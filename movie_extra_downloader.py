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
import codecs
import json
import hashlib
import yt_dlp
from _socket import timeout
from requests import Request, Session

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


def get_keyword_list(string):

    ret = ' ' + get_clean_string(string).lower() + ' '
    ret = (ret.replace(' the ', '')
              .replace(' in ', '')
              .replace(' a ', '')
              .replace(' by ', '')
              .replace(' for ', '')
              .replace(' is ', '')
              .replace(' am ', '')
              .replace(' an ', '')
              .replace(' in ', '')
              .replace(' with ', '')
              .replace(' from ', '')
              .replace(' and ', '')
              .replace(' movie ', '')
              .replace(' trailer ', '')
              .replace(' interview ', '')
              .replace(' interviews ', '')
              .replace(' scenes ', '')
              .replace(' scene ', '')
              .replace(' official ', '')
              .replace(' hd ', '')
              .replace(' hq ', '')
              .replace(' lq ', '')
              .replace(' 1080p ', '')
              .replace(' 720p ', '')
              .replace(' of ', ''))


    return list(set(space_cleanup(ret).split(' ')))


def get_clean_string(string):
    ret = ' ' + string.lower() + ' '

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

    return space_cleanup(ret)


def space_cleanup(string):
    ret = string
    while '  ' in ret:
        ret = ret.replace('  ', ' ')
    while ret.endswith(' '):
        ret = ret[:-1]
    while ret.startswith(' '):
        ret = ret[1:]
    return ret


def retrieve_web_page(url, params, page_name='page'):

    session = Session()
    response = None
    log.info('Browsing %s.', page_name)

    for tries in range(1, 10):
        try:
            request = Request('GET', url)
            prepped = session.prepare_request(request)
            response = session.send(prepped, timeout=2)
            break
        except UnicodeEncodeError as e:

            log.error('Failed to download %s : %s. Skipping.', page_name, e)
            break
        except timeout:

            if tries > 5:
                log.error('You might have lost internet connection.')
                break

            time.sleep(1)
            log.error('Failed to download %s : %s : timed out. Retrying.', page_name, e)

        except HTTPError as e:

            log.error('Failed to download %s : %s. Skipping.', page_name, e)
            break
        except URLError:

            if tries > 3:
                log.error('You might have lost internet connection.')
                raise

            time.sleep(1)
            log.error('Failed to download %s', page_name + '. Retrying.')

    return response


def search_tmdb_by_id(tmdb_id, extra_types):
    url = settings.tmdb_api_url + '/' + args.mediatype + '/' + str(tmdb_id) + '/videos' \
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


def search_tmdb_by_title(title, mediatype):
    url = settings.tmdb_api_url + '/search/' + mediatype \
        + '?api_key=' + settings.tmdb_api_key \
        + '&query=' + quote(title.encode('utf-8')) \
        + '&language=en-US&page=1&include_adult=false'
    log.debug('url: %s', url.replace(settings.tmdb_api_key, "[masked]"))
    response = retrieve_web_page(url, 'tmdb movie search page')
    data = json.loads(response.text)
    response.close()

    return data


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
                    except yt_dlp.DownloadError as e:
                        if 'ERROR: Unable to download webpage:' in e.args[0]:
                            if tries > 3:
                                log.error('hey, there: error!!!')
                                raise
                            log.error('failed to get video data, retrying')
                            time.sleep(1)

                return youtube_info

            youtube_video = get_video_data()

            if not youtube_video:
                return None

            youtube_video['title'] = get_clean_string(youtube_video['title'])
            youtube_video['extra_type'] = url['extra_type']

            if youtube_video['view_count'] is None:
                youtube_video['view_count'] = 100

            if youtube_video['view_count'] < 100:
                youtube_video['view_count'] = 100

            if youtube_video['average_rating'] is None:
                youtube_video['average_rating'] = 0

            if youtube_video['view_count'] is None:
                youtube_video['view_count'] = 0

            youtube_video['adjusted_rating'] = youtube_video['average_rating'] * \
                (1 - 1 / (youtube_video['view_count'] / 60) ** 0.5)

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

            if youtube_video['upload_date']:
                if youtube_video['upload_date'] is not None:
                    date_str = youtube_video['upload_date']
                    upload_date = date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
                    time_delta = date.today() - upload_date
                    youtube_video['views_per_day'] = youtube_video['view_count'] / \
                        (365 + time_delta.total_seconds() / 60 / 60 / 24)
                else:
                    log.error('no "upload_date"!!!')
                    youtube_video['views_per_day'] = 0
            else:
                log.error('no "upload_date"!!!')
                youtube_video['views_per_day'] = 0

            return youtube_video

        url_list = []

        if self.record.tmdb_id:
            urls = search_tmdb_by_id(self.record.tmdb_id, settings.extra_types)
            log.debug('urls: %s', urls)
        else:
            log.error('tmdb_id is missing')

        if urls:
            url_list += urls

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
            if not settings.force:
                for youtube_video_id in self.record.records:
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
                except yt_dlp.DownloadError as e:

                    if tries > 3:
                        if str(e).startswith('ERROR: Did not get any data blocks'):
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

            self.record.records.append({
                'youtube_video_id': youtube_video_id,
                'file_path': extra_type,
                'file_name': file_name,
                'extra_type': extra_type,
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
            if settings.extra_types == 'theme-music':
                target_path = os.path.join(self.record.full_path, 'theme.mp3')
            else:
                target_path = os.path.join(self.record.full_path, extra_type, file_name)

            log.debug('Moving file to %s folder', extra_type)
            copy_file()
            record_file()


class Settings:
    def __init__(self):
        default_config = configparser.ConfigParser()
        default_config.read(os.path.join(os.path.dirname(sys.argv[0]),'default_config.cfg'))

        self.tmp_folder_root = os.path.join(os.path.dirname(sys.argv[0]), 'tmp')
        self.records = os.path.join(os.path.dirname(sys.argv[0]), 'records')
        self.tmdb_api_url = 'https://api.themoviedb.org/3'
        self.tmdb_api_key = default_config.get('SETTINGS', 'tmdb_api_key')
        self.extra_types = json.loads(default_config.get('SETTINGS', 'extra_types'))
        self.force = default_config.get('SETTINGS', 'force')
        self.youtube_dl_arguments = json.loads(default_config.get('SETTINGS', 'youtube_dl_arguments'))

class Record:

    def __init__(self, tmdb_id=None, json_dict=None):

        self.name = None

        self.tmdb_id = None
        self.movie_title = None
        self.movie_original_title = None
        self.movie_original_title_keywords = None
        self.movie_release_year = None
        self.movie_title_keywords = []

        self.records = []

        self.update_all(tmdb_id=tmdb_id)

    @classmethod
    def load_record(cls, file_name):
        with open(file_name, 'r', encoding='utf-8') as load_file:
            return Record(json_dict=json.load(load_file))


    def update_all(self, tmdb_id=None):

        self.name = os.path.split(args.directory)[1]
        self.full_path = args.directory
        self.update_movie_info(tmdb_id)


    def update_movie_info(self, tmdb_id=None):

        def get_info_from_directory():
            clean_name_tuple = get_clean_string(self.name).split(' ')

            if len(clean_name_tuple) > 1 \
                    and any(clean_name_tuple[-1] == str(year) for year in range(1896, date.today().year + 2)):
                self.movie_release_year = int(clean_name_tuple[-1])
                self.movie_title = ' '.join(clean_name_tuple[:-1])
                self.movie_original_title = ' '.join(clean_name_tuple[:-1])
            else:
                self.movie_release_year = None
                self.movie_title = ' '.join(clean_name_tuple)
                self.movie_original_title = ' '.join(clean_name_tuple)
            self.movie_title_keywords = get_keyword_list(self.movie_title)
            self.movie_original_title_keywords = get_keyword_list(self.movie_original_title)

            return True

        def get_tmdb_details_data(tmdb_id):
            url = settings.tmdb_api_url + '/' + args.mediatype + '/' + str(tmdb_id) \
                + '?api_key=' + settings.tmdb_api_key \
                + '&language=en-US'
            log.debug('url: %s', url.replace(settings.tmdb_api_key, "[masked]"))
            response = retrieve_web_page(url, 'tmdb media details')
            data = json.loads(response.text)
            response.close()

            return data

        def get_info_from_details():
            details_data = get_tmdb_details_data(tmdb_id)
            if details_data is not None:
                try:
                    self.tmdb_id = details_data['id']
                    self.movie_title = details_data['title']
                    self.movie_original_title = details_data['original_title']
                    self.movie_title_keywords = get_keyword_list(details_data['title'])
                    self.movie_original_title_keywords = get_keyword_list(details_data['original_title'])

                    if len((details_data['release_date'])[:4]) == 4:
                        self.movie_release_year = int((details_data['release_date'])[:4])
                    else:
                        self.movie_release_year = None
                    return True
                except KeyError:
                    return False
                except TypeError:
                    return False
            else:
                log.error('Nothing found')
                return False


        def search_by_title():
            search_data = search_tmdb_by_title(self.movie_title, args.mediatype)

            if search_data is None or search_data['total_results'] == 0:
                log.error('Nothing foung by title')
                return False

            movie_data = None
            movie_backup_data = None

            if self.movie_release_year is None:
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
                        if str(self.movie_release_year) == (data['release_date'])[:4]:
                            movie_data = data
                        elif (data['release_date'])[6:8] in ['09', '10', '11', '12'] \
                                and str(self.movie_release_year - 1) == (data['release_date'])[:4]:
                            movie_data = data
                        elif (data['release_date'])[6:8] in ['01', '02', '03', '04'] \
                                and str(self.movie_release_year + 1) == (data['release_date'])[:4]:
                            movie_data = data
                    elif movie_backup_data is None:
                        if str(self.movie_release_year - 1) == (data['release_date'])[:4]:
                            movie_backup_data = data
                        elif str(self.movie_release_year + 1) == (data['release_date'])[:4]:
                            movie_backup_data = data

                if movie_data is None and movie_backup_data is not None:
                    log.info( 'None of the search results had a correct release year, picking the next best result')
                    movie_data = movie_backup_data

                if movie_data is None:
                    movie_data = search_data['results'][0]

            self.tmdb_id = movie_data['id']
            if args.mediatype == 'movie':
                self.movie_title = get_clean_string(movie_data['title'])
                self.movie_original_title = get_clean_string(movie_data['original_title'])
                self.movie_title_keywords = get_keyword_list(movie_data['title'])
                self.movie_original_title_keywords = get_keyword_list(movie_data['original_title'])
                if len((movie_data['release_date'])[:4]) == 4:
                    self.movie_release_year = int((movie_data['release_date'])[:4])
                else:
                    self.movie_release_year = None
            else:
                self.movie_title = get_clean_string(movie_data['name'])
                self.movie_original_title = get_clean_string(movie_data['original_name'])
                self.movie_title_keywords = get_keyword_list(movie_data['name'])
                if len((movie_data['first_air_date'])[:4]) == 4:
                    self.movie_release_year = int((movie_data['first_air_date'])[:4])
                else:
                    self.movie_release_year = None
            return True

        if tmdb_id is not None:
            if get_info_from_details():
                return True

        if get_info_from_directory():
            if search_by_title():
                return True
        else:
            return False


    def save_record(self, save_path):
        if not os.path.isdir(save_path):
            os.mkdir(os.path.join(save_path))
        with open(os.path.join(save_path, self.name + ".json"), 'w') as save_file:
            json.dump(self.__dict__, save_file, indent = 4)


def download_extra(record):
    finder = ExtraFinder(record)
    log.info('processing: %s', record.name)
    finder.search()

    for youtube_video in finder.youtube_videos:
        log.info('extra_type: %s', youtube_video['extra_type'])
        log.info('webpage_url: %s', youtube_video['webpage_url'])
        log.info('adjusted_rating: %s', str(youtube_video['adjusted_rating']))
        log.info('format: %s', youtube_video['format'])
        log.info('views_per_day: %s', str(youtube_video['views_per_day']))

    log.info(record.name)


    for youtube_video in finder.youtube_videos:
        log.info('%s : %s (%s)',
                youtube_video['webpage_url'],
                youtube_video['format'],
                str(youtube_video['adjusted_rating']))
    for youtube_video in finder.play_trailers:
        log.info('play trailer: %s : %s',
                youtube_video['webpage_url'],
                youtube_video['format'])
    log.info('downloading for: %s', record.name)
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

    try:
        record_path = os.path.join(records, os.path.split(args.directory)[1] + ".json")
        if not args.force and os.path.exists(record_path):
            record = Record.load_record(record_path)
        else:
            record = Record(tmdb_id=args.tmdbid)

    if record.tmdb_id is None:
        sys.exit()

    if args.replace:
        args.force = True

    if args.force:
        old_records = record.records
        record.records = []
        for record in old_records:
            if record != settings.extra_types:
                record.records.append(record)
        force = True

    if args.replace:
        for extra_type in settings.extra_types:
            shutil.rmtree(os.path.join(record.full_path,
                        extra_type),
                        ignore_errors=True)

    if not os.path.isdir(settings.tmp_folder_root):
        os.mkdir(settings.tmp_folder_root)

    download_extra(record)
    record.save_record(settings.records)

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
