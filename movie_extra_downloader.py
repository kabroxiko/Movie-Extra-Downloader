#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""Search and download media extras."""
from bisect import bisect
from datetime import date

from urllib.parse import quote
from urllib.error import URLError, HTTPError

import os
import sys
import logging
import configparser
import argparse
import time
import shutil
import json
import yt_dlp
from _socket import timeout
from requests import Request, Session

def get_clean_string(string):
    ret = string

    ret = (ret.replace('(', '')
              .replace(')', '')
              .replace('[', '')
              .replace(']', '')
              .replace('{', '')
              .replace('}', '')
              .replace(':', '')
              .replace(';', '')
              .replace('?', '')
              .replace("'", '')
              .replace('\xe2\x80\x99', '')
              .replace('\xc2\xb4', '')
              .replace('`', '')
              .replace('*', '')
              .replace('.', '')
              .replace('\xc2\xb7', '')
              .replace(' -', '')
              .replace('- ', '')
              .replace('_', '')
              .replace(' + ', '')
              .replace('+', '')
              .replace(' : ', '')
              .replace('/ ', '')
              .replace(' /', '')
              .replace(' & ', ' '))


    ret_tup = ret.split(' ')
    ret_count = 0
    for ret_tup_count in range(len(ret_tup) - 1):
        if len(ret_tup[ret_tup_count]) == 1 \
                and len(ret_tup[ret_tup_count + 1]) == 1:
            ret_count += 1
            ret = ret[:ret_count] + ret[ret_count:ret_count + 1].replace(' ', '.') + ret[ret_count + 1:]
            ret_count += 1
        else:
            ret_count += len(ret_tup[ret_tup_count]) + 1

    while '  ' in ret:
        ret = ret.replace('  ', ' ')
    while ret.endswith(' '):
        ret = ret[:-1]
    while ret.startswith(' '):
        ret = ret[1:]

    return ret


def retrieve_web_page(url, page_name='page'):

    session = Session()
    response = None
    log.info('Browsing %s.', page_name)

    for tries in range(1, 10):
        try:
            request = Request('GET', url)
            prepped = session.prepare_request(request)
            response = session.send(prepped, timeout=2)
            break
        except UnicodeEncodeError as error:

            log.error('Failed to download %s : %s. Skipping.', page_name, error)
            break
        except timeout:

            if tries > 5:
                log.error('You might have lost internet connection.')
                break

            time.sleep(1)
            log.error('Failed to download %s : %s : timed out. Retrying.', page_name, error)

        except HTTPError as error:

            log.error('Failed to download %s : %s. Skipping.', page_name, error)
            break
        except URLError:

            if tries > 3:
                log.error('You might have lost internet connection.')
                raise

            time.sleep(1)
            log.error('Failed to download %s', page_name + '. Retrying.')

    return response


def search_tmdb_by_id(tmdb_id, extra_types, media_type):
    url = settings.tmdb_api_url + '/' + media_type + '/' + str(tmdb_id) + '/videos' \
        + '?api_key=' + settings.tmdb_api_key \
        + '&language=en-US'
    log.debug('url: %s', url.replace(settings.tmdb_api_key, "[masked]"))
    response = retrieve_web_page(url, 'tmdb media videos')
    data = json.loads(response.text)
    response.close()
    if len(data['results']) == 0:
        log.error('No videos found')
        return None

    log.debug('Search for: %s', extra_types)
    ret_url_list = []
    for data in data['results']:
        log.debug('Found: type=%s key=%s', data['type'], data['key'])
        extra_type = None
        if ('Behind The Scenes' in extra_types and data['type'] == 'Behind the Scenes'):
            extra_type = 'Behind the Scenes'
        elif ('Featurettes' in extra_types and data['type'] == 'Featurette'):
            extra_type = 'Featurettes'
        elif ('Scenes' in extra_types and data['type'] == 'Clip'):
            extra_type = 'Scenes'
        elif ('Trailers' in extra_types and (data['type'] == 'Trailer' or data['type'] == 'Teaser')):
            extra_type = 'Trailers'
        elif ('Others' in extra_types and data['type'] == 'Bloopers'):
            extra_type = 'Others'

        if extra_type is not None:
            ret_url_list.append({"extra_type": extra_type, "link": 'https://www.youtube.com/watch?v=' + data['key']})

    return ret_url_list


class ExtraFinder:

    conn_errors = 0

    def __init__(self, record):

        self.record = record
        self.complete = True

        self.youtube_videos = []
        self.play_trailers = []

    def search(self):

        def create_youtube_video():

            def get_video_data():
                youtube_info = None
                for tries in range(1, 11):
                    try:
                        with yt_dlp.YoutubeDL({'quiet': True,
                                               'socket_timeout': '3',
                                               'logger': log}) as ydl:
                            youtube_info = ydl.extract_info(url['link'], download=False)
                            break
                    except yt_dlp.DownloadError as error:
                        if 'This video is not available' in error.args[0] \
                                or 'The uploader has not made this video available in your country' in error.args[0] \
                                or 'Private video' in error.args[0]:
                            break
                        if 'ERROR: Unable to download webpage:' in error.args[0]:
                            if tries > 3:
                                log.error('hey, there: error!!!')
                                raise
                            log.error('failed to get video data, retrying')
                            time.sleep(1)

                return youtube_info

            youtube_video = get_video_data()

            if not youtube_video:
                return None

            log.debug('duration: %s', youtube_video['duration'])
            if youtube_video['duration'] >= settings.max_length:
                log.debug('This video is longer than %s: %s', settings.max_length, youtube_video['title'])
                return None

            youtube_video['title'] = get_clean_string(youtube_video['title'])
            youtube_video['extra_type'] = url['extra_type']

            if youtube_video['width'] is None or youtube_video['height'] is None:
                youtube_video['resolution_ratio'] = 1
                youtube_video['resolution'] = 144
            else:
                youtube_video['resolution_ratio'] = youtube_video['width'] / youtube_video['height']

                resolution = max(int(youtube_video['height']), int(youtube_video['width'] / 16 * 9))
                resolutions = [
                    144,
                    240,
                    360,
                    480,
                    720,
                    1080,
                    1440,
                    2160,
                ]

                youtube_video['resolution'] = resolutions[bisect(resolutions, resolution * 1.2) - 1]

            return youtube_video

        url_list = []

        if self.record.tmdb_id:
            url_list += search_tmdb_by_id(self.record.tmdb_id, settings.extra_types, self.record.media_type)
            log.debug('urls: %s', url_list)
        else:
            log.error('tmdb_id is missing')

        for url in url_list:
            if not any(url['link'] in youtube_video['webpage_url']
                       or youtube_video['webpage_url'] in url['link']
                       for youtube_video in self.youtube_videos):
                if 'youtube.com/watch?v=' not in url['link']:
                    continue
                video = create_youtube_video()

                if video:
                    self.youtube_videos.append(video)
                    if not video['categories']:
                        self.play_trailers.append(video)

    def download_videos(self, tmp_file):

        downloaded_videos_meta = []

        arguments = settings.youtube_dl_arguments
        arguments['encoding'] = 'utf-8'
        arguments['logger'] = log
        arguments['outtmpl'] = os.path.join(tmp_file, '%(title)s.%(ext)s')
        for (key, value) in arguments.items():
            if isinstance(value, str):
                if value.lower() == 'false' or value.lower() == 'no':
                    arguments[key] = ''

        count = 0

        for youtube_video in self.youtube_videos[:]:
            if not args.force:
                for youtube_video_id in self.record.extras:
                    if youtube_video_id == youtube_video['id']:
                        continue

            for tries in range(1, 11):
                try:
                    with yt_dlp.YoutubeDL(arguments) as ydl:
                        info = ydl.extract_info(youtube_video['webpage_url'])
                        info["extra_type"] = youtube_video['extra_type']
                        meta = ydl.sanitize_info(info)
                        downloaded_videos_meta.append(meta)
                        count += 1
                        break
                except yt_dlp.DownloadError as error:

                    if tries > 3:
                        if str(error).startswith('ERROR: Did not get any data blocks'):
                            return None
                        log.error('failed to download the video.')
                        break
                    log.error('failed to download the video. retrying')
                    time.sleep(3)

        return downloaded_videos_meta

    def move_videos(self, downloaded_videos_meta, tmp_folder):

        def copy_file():
            if not os.path.isdir(os.path.split(target_path)[0]):
                os.mkdir(os.path.split(target_path)[0])
            shutil.move(source_path, target_path)

        def record_file():
            youtube_video_id = 'unknown'
            for meta in downloaded_videos_meta:
                youtube_video_id = meta['id']

            self.record.extras.append({
                'youtube_video_id': youtube_video_id,
                'extra_type': extra_type,
                'file_name': file_name,
            })

        for file_name in os.listdir(tmp_folder):
            for video_meta in downloaded_videos_meta:
                if video_meta['title'] in file_name.replace('\u29f8','\u002f') \
                                                   .replace('\uff02','\u0022') \
                                                   .replace('\uff1a','\u003a') \
                                                   .replace('\uff1f','\u003f') \
                                                   .replace('\uff5c','\u007c'):
                    extra_type = video_meta['extra_type']
                    break
            source_path = os.path.join(tmp_folder, file_name)
            target_path = os.path.join(args.directory, extra_type, file_name)

            log.debug('Moving file to %s folder', extra_type)
            copy_file()
            record_file()


class Settings:
    def __init__(self):
        default_config = configparser.ConfigParser()
        default_config.read(os.path.join(os.path.dirname(sys.argv[0]),'default_config.cfg'))

        self.tmp_folder_root = os.path.join(os.path.dirname(sys.argv[0]), 'tmp')
        self.record_folder = os.path.join(os.path.dirname(sys.argv[0]), 'records')
        self.tmdb_api_url = 'https://api.themoviedb.org/3'
        self.tmdb_api_key = default_config.get('SETTINGS', 'tmdb_api_key')
        self.max_length = 200
        self.extra_types = json.loads(default_config.get('SETTINGS', 'extra_types'))
        self.youtube_dl_arguments = json.loads(default_config.get('SETTINGS', 'youtube_dl_arguments'))

class Record:

    def __init__(self):

        self.tmdb_id = None
        self.full_path = args.directory
        self.media_type = args.mediatype
        self.title = None
        if self.media_type == 'movie':
            self.original_title = None
            self.release_date = None
        else:
            self.original_name = None
            self.first_air_date = None
        self.extras = []

        self.update_all()

    @classmethod
    def load_record(cls, file_name):
        with open(file_name, 'r', encoding='utf-8'):
            return Record()


    def update_all(self):

        self.title = os.path.split(args.directory)[1]

        def get_info_from_directory_name():
            clean_name_tuple = get_clean_string(self.title).split(' ')

            if self.media_type == 'movie':
                if len(clean_name_tuple) > 1 \
                        and any(clean_name_tuple[-1] == str(year) for year in range(1896, date.today().year + 2)):
                    self.release_date = int(clean_name_tuple[-1])
                    self.title = ' '.join(clean_name_tuple[:-1])
                else:
                    self.release_date = None
                    self.title = ' '.join(clean_name_tuple)
            else:
                if len(clean_name_tuple) > 1 \
                        and any(clean_name_tuple[-1] == str(year) for year in range(1896, date.today().year + 2)):
                    self.first_air_date = int(clean_name_tuple[-1])
                    self.title = ' '.join(clean_name_tuple[:-1])
                else:
                    self.first_air_date = None
                    self.title = ' '.join(clean_name_tuple)

            return True

        def get_tmdb_details_data():
            url = settings.tmdb_api_url + '/' + self.media_type + '/' + str(self.tmdb_id) \
                + '?api_key=' + settings.tmdb_api_key \
                + '&language=en-US'
            log.debug('url: %s', url.replace(settings.tmdb_api_key, "[masked]"))
            response = retrieve_web_page(url, 'tmdb media details')
            data = json.loads(response.text)
            response.close()

            return data

        def get_info_from_details():
            details_data = get_tmdb_details_data()
            if details_data is not None:
                try:
                    if len((details_data['release_date'])[:4]) == 4:
                        self.release_date = int((details_data['release_date'])[:4])
                    else:
                        self.release_date = None
                    return True
                except KeyError:
                    return False
                except TypeError:
                    return False
            else:
                log.error('Nothing found')
                return False


        def search_tmdb_by_title():
            url = settings.tmdb_api_url + '/search/' + self.media_type \
                + '?api_key=' + settings.tmdb_api_key \
                + '&query=' + quote(self.title.encode('utf-8')) \
                + '&language=en-US&page=1&include_adult=false'
            log.debug('url: %s', url.replace(settings.tmdb_api_key, "[masked]"))
            response = retrieve_web_page(url, 'tmdb movie search page')
            search_data = json.loads(response.text)
            response.close()

            if search_data is None or search_data['total_results'] == 0:
                log.error('Nothing foung by title')
                return False

            movie_data = None
            movie_backup_data = None

            if (self.media_type == 'movie' and self.release_date is None) \
                 or (self.media_type == 'tv' and self.first_air_date is None):
                movie_data = search_data['results'][0]
            else:

                for data in (search_data['results'])[:5]:
                    try:
                        if data['release_date'] is None:
                            data['release_date'] = '000000000000000'
                            continue
                    except KeyError:
                        data['release_date'] = '000000000000000'
                        continue
                    if movie_data is None:
                        if str(self.release_date) == (data['release_date'])[:4]:
                            movie_data = data
                        elif (data['release_date'])[6:8] in ['09', '10', '11', '12'] \
                                and str(self.release_date - 1) == (data['release_date'])[:4]:
                            movie_data = data
                        elif (data['release_date'])[6:8] in ['01', '02', '03', '04'] \
                                and str(self.release_date + 1) == (data['release_date'])[:4]:
                            movie_data = data
                    elif movie_backup_data is None:
                        if str(self.release_date - 1) == (data['release_date'])[:4]:
                            movie_backup_data = data
                        elif str(self.release_date + 1) == (data['release_date'])[:4]:
                            movie_backup_data = data

                if movie_data is None and movie_backup_data is not None:
                    log.info( 'None of the search results had a correct release year, picking the next best result')
                    movie_data = movie_backup_data

                if movie_data is None:
                    movie_data = search_data['results'][0]

            self.tmdb_id = movie_data['id']
            if self.media_type == 'movie':
                self.title = get_clean_string(movie_data['title'])
                self.original_title = get_clean_string(movie_data['original_title'])
                if len((movie_data['release_date'])[:4]) == 4:
                    self.release_date = int((movie_data['release_date'])[:4])
                else:
                    self.release_date = None
            else:
                self.title = get_clean_string(movie_data['original_name'])
                self.original_name = get_clean_string(movie_data['original_name'])
                if len((movie_data['first_air_date'])[:4]) == 4:
                    self.first_air_date = int((movie_data['first_air_date'])[:4])
                else:
                    self.first_air_date = None
            return True

        if not get_info_from_directory_name():
            return False

        if not search_tmdb_by_title():
            return False

        if not get_info_from_details():
            return False

        return True

    def save_record(self, save_path):
        if not os.path.isdir(save_path):
            os.mkdir(os.path.join(save_path))
        with open(os.path.join(save_path, os.path.split(args.directory)[1] + ".json"), 'w') as save_file:
            json.dump(self.__dict__, save_file, indent = 4)


def download_extra(record):
    finder = ExtraFinder(record)
    log.info('processing: %s', record.title)
    finder.search()

    for youtube_video in finder.youtube_videos:
        log.info('extra_type: %s', youtube_video['extra_type'])
        log.info('webpage_url: %s', youtube_video['webpage_url'])
        log.info('format: %s', youtube_video['format'])

    log.info(record.title)

    for youtube_video in finder.youtube_videos:
        log.info('%s : %s',
                youtube_video['webpage_url'],
                youtube_video['format'])
    for youtube_video in finder.play_trailers:
        log.info('play trailer: %s : %s',
                youtube_video['webpage_url'],
                youtube_video['format'])
    log.info('downloading for: %s', record.title)
    count = 0
    tmp_folder = os.path.join(settings.tmp_folder_root, 'tmp_0')
    while True:
        try:
            while os.listdir(tmp_folder):
                if count == 0 and not tmp_folder.endswith('_0'):
                    tmp_folder += '_0'
                else:
                    tmp_folder = tmp_folder[:-2] + '_' + str(count)
                    count += 1
            break
        except FileNotFoundError:
            os.mkdir(tmp_folder)

    # Actually download files
    downloaded_videos_meta = finder.download_videos(tmp_folder)

    # Actually move files
    if downloaded_videos_meta:
        finder.move_videos(downloaded_videos_meta, tmp_folder)


def handle_directory():
    log.info('working on record: %s', args.directory)

    record_path = os.path.join(settings.record_folder, os.path.split(args.directory)[1] + ".json")
    if not args.force and os.path.exists(record_path):
        record = Record.load_record(record_path)
    else:
        record = Record()

    if record.tmdb_id is None:
        sys.exit()

    if args.replace:
        args.force = True

    if args.force:
        record.extras = []
        for record in record.extras:
            if record != settings.extra_types:
                record.extras.append(record)

    if args.replace:
        for extra_type in settings.extra_types:
            shutil.rmtree(os.path.join(args.directory, extra_type),
                          ignore_errors=True)

    if not os.path.isdir(settings.tmp_folder_root):
        os.mkdir(settings.tmp_folder_root)

    download_extra(record)
    record.save_record(settings.record_folder)

parser = argparse.ArgumentParser()
parser.add_argument('-d', '--directory', help='directory to search extras for')
parser.add_argument('-t', '--tmdbid', help='tmdb id to search extras for')
parser.add_argument('-m', '--mediatype', help='media type to search extras for')
parser.add_argument('-f', '--force', action='store_true', help='force scan the directories')
parser.add_argument('-r', '--replace', action='store_true', help='remove and ban the existing extra')
args = parser.parse_args()

if args.directory and os.path.split(args.directory)[1] == '':
    args.directory = os.path.split(args.directory)[0]

# Setup logger

logging.basicConfig(level=logging.DEBUG, format='%(message)s')
log = logging.getLogger('med')

# Retrieve Required Variables

if os.environ.get('sonarr_eventtype') == 'Test':
    log.info('Test Sonarr works')
    sys.exit(0)
elif os.environ.get('radarr_eventtype') == 'Test':
    log.info('Test Radarr works')
    sys.exit(0)
elif 'sonarr_eventtype' in os.environ:
    args.directory = os.environ.get('sonarr_series_path')
    args.mediatype = 'tv'
    log.info('directory: %s', args.directory)
elif 'radarr_eventtype' in os.environ:
    args.directory = os.environ.get('radarr_movie_path')
    args.tmdbid = os.environ.get('radarr_movie_tmdbid')
    args.mediatype = 'movie'
    log.info('directory: %s', args.directory)

settings = Settings()

if not args.mediatype:
    log.error('please specify media type (-m) to search extras for')
    sys.exit(1)

if args.directory:
    handle_directory()
else:
    log.error('please specify a directory (-d) to search extras for')

try:
    shutil.rmtree(settings.tmp_folder_root, ignore_errors=True)
except FileNotFoundError:
    pass
os.mkdir(settings.tmp_folder_root)

sys.exit()
