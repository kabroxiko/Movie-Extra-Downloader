#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""Search and download media extras."""
from bisect import bisect
from datetime import date

from urllib.parse import quote
from urllib.request import urlopen
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
import traceback
import hashlib
import yt_dlp
from _socket import timeout

parser = argparse.ArgumentParser()
parser.add_argument('-d', '--directory',
                    help='directory to search extras for')
parser.add_argument('-l', '--library',
                    help='library of directories to search extras for')
parser.add_argument('-t', '--tmdbid',
                    help='tmdb id to search extras for')
parser.add_argument('-m', '--mediatype',
                    help='media type to search extras for')
parser.add_argument('-f', '--force', action='store_true',
                    help='force scan the directories')
parser.add_argument('-r', '--replace', action='store_true',
                    help='remove and ban the existing extra')
args = parser.parse_args()

if args.directory and os.path.split(args.directory)[1] == '':
    args.directory = os.path.split(args.directory)[0]

if args.library and os.path.split(args.library)[1] == '':
    args.library = os.path.split(args.library)[0]

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


def make_list_from_string(string, delimiter=',',
                          remove_spaces_next_to_delimiter=True):
    if remove_spaces_next_to_delimiter:
        while ' ' + delimiter in string:
            string = string.replace(' ' + delimiter, delimiter)
        while delimiter + ' ' in string:
            string = string.replace(delimiter + ' ', delimiter)

    return string.split(delimiter)


def apply_query_template(template, keys):
    ret = template
    for (key, value) in keys.items():
        if isinstance(value, str):
            ret = ret.replace('{' + key + '}', value)
        elif isinstance(value, int):
            ret = ret.replace('{' + key + '}', str(value))
        elif isinstance(value, float):
            ret = ret.replace('{' + key + '}', str(value))

    return space_cleanup(ret)


def replace_roman_numbers(string):
    ret = ' ' + string.lower() + ' '

    ret = ret.replace(
        ' ix ',
        ' 9 ').replace(
        ' viiii ',
        ' 9 ').replace(
        ' viii ',
        ' 8 ').replace(
        ' vii ',
        ' 7 ').replace(
        ' vi ',
        ' 6 ').replace(
        ' iv ',
        ' 4 ').replace(
        ' iiii ',
        ' 4 ').replace(
        ' iii ',
        ' 3 ').replace(
        ' ii ',
        ' 2 ').replace(
        ' trailer 4 ',
        ' trailer ').replace(
        ' trailer 3 ',
        ' trailer ').replace(
        ' trailer 2 ',
        ' trailer ').replace(
        ' trailer 1 ',
        ' trailer ')

    return space_cleanup(ret)


def get_keyword_list(string):

    ret = ' ' + get_clean_string(string).lower() + ' '
    ret = ret.replace(
        ' the ',
        ' ').replace(
        ' in ',
        ' ').replace(
        ' a ',
        ' ').replace(
        ' by ',
        ' ').replace(
        ' for ',
        ' ').replace(
        ' is ',
        ' ').replace(
        ' am ',
        ' ').replace(
        ' an ',
        ' ').replace(
        ' in ',
        ' ').replace(
        ' with ',
        ' ').replace(
        ' from ',
        ' ').replace(
        ' and ',
        ' ').replace(
        ' movie ',
        ' ').replace(
        ' trailer ',
        ' ').replace(
        ' interview ',
        ' ').replace(
        ' interviews ',
        ' ').replace(
        ' scenes ',
        ' ').replace(
        ' scene ',
        ' ').replace(
        ' official ',
        ' ').replace(
        ' hd ',
        ' ').replace(
        ' hq ',
        ' ').replace(
        ' lq ',
        ' ').replace(
        ' 1080p ',
        ' ').replace(
        ' 720p ',
        ' ').replace(
        ' of ',
        ' ')

    return list(set(space_cleanup(ret).split(' ')))


def get_clean_string(string):
    ret = ' ' + string.lower() + ' '

    ret = ret.replace(
        '(',
        '').replace(
        ')',
        '').replace(
        '[',
        '').replace(
        ']',
        '').replace(
        '{',
        '').replace(
        '}',
        '').replace(
        ':',
        '').replace(
        ';',
        '').replace(
        '?',
        '').replace(
        "'",
        '').replace(
        '\xe2\x80\x99',
        '').replace(
        '\xc2\xb4',
        '').replace(
        '`',
        '').replace(
        '*',
        ' ').replace(
        '.',
        ' ').replace(
        '\xc2\xb7',
        '-').replace(
        ' -',
        ' ').replace(
        '- ',
        ' ').replace(
        '_',
        ' ').replace(
        ' + ',
        ' : ').replace(
        '+',
        '/').replace(
        ' : ',
        ' + ').replace(
        '/ ',
        ' ').replace(
        ' /',
        ' ').replace(
        ' & ',
        ' ')

    ret_tup = ret.split(' ')
    ret_count = 0
    for ret_tup_count in range(len(ret_tup) - 1):
        if len(ret_tup[ret_tup_count]) == 1 \
                and len(ret_tup[ret_tup_count + 1]) == 1:
            ret_count += 1
            ret = ret[:ret_count] + ret[ret_count:ret_count +
                                        1].replace(' ', '.') + ret[ret_count + 1:]
            ret_count += 1
        else:
            ret_count += len(ret_tup[ret_tup_count]) + 1

    return space_cleanup(replace_roman_numbers(ret))


def space_cleanup(string):
    ret = string
    while '  ' in ret:
        ret = ret.replace('  ', ' ')
    while ret.endswith(' '):
        ret = ret[:-1]
    while ret.startswith(' '):
        ret = ret[1:]
    return ret


def hash_file(file_path):
    response = None
    if not os.path.isdir(file_path):
        md5 = hashlib.md5()
        with open(file_path, 'rb') as file:
            for i in range(10):
                data = file.read(2 ** 20)
                if not data:
                    break
                md5.update(data)
        response = md5.hexdigest()
    return response


def retrieve_web_page(url, page_name='page'):

    response = None
    log.info('Downloading %s', page_name + '.')

    for tries in range(1, 10):
        try:
            response = urlopen(url, timeout=2)
            break
        except UnicodeEncodeError as e:

            log.error('Failed to download %s : %s. Skipping.', page_name, str(e))
            break
        except timeout:

            if tries > 5:
                log.error('You might have lost internet connection.')
                break

            time.sleep(1)
            log.error('Failed to download %s : %s : timed out. Retrying.', page_name, str(e))

        except HTTPError as e:

            log.error('Failed to download %s : %s. Skipping.', page_name, str(e))
            break
        except URLError:

            if tries > 3:
                log.error('You might have lost internet connection.')
                raise

            time.sleep(1)
            log.error('Failed to download %s', page_name + '. Retrying.')

    return response


def tmdb_search(
        tmdb_id,
        extra_type,
        limit,):
    ret_url_list = []
    url = 'https://api.themoviedb.org/3/' + args.mediatype + '/' \
        + str(tmdb_id) + '/videos' + '?api_key=' + tmdb_api_key \
        + '&language=en-US'
    log.debug('url: %s', url)
    response = retrieve_web_page(url, 'tmdb movie videos')
    if response is None:
        return None
    data = json.loads(response.read().decode('utf-8'))
    response.close()

    log.debug('details_data: %s', str(data))
    log.debug('Search for: %s', extra_type)
    for data in data['results']:
        log.debug('Found: type=%s key=%s', data['type'], data['key'])
        if extra_type == 'Behind The Scenes' \
            and data['type'] == 'Behind the Scenes' or extra_type == 'Featurettes' \
            and data['type'] == 'Featurette' or extra_type == 'Scenes' \
            and data['type'] == 'Clip' or extra_type == 'Trailers' \
            and (data['type'] == 'Trailer' or data['type'] == 'Teaser') \
            or extra_type == 'Others' \
            and data['type'] == 'Bloopers':

            ret_url_list.append('https://www.youtube.com/watch?v=' + data['key'])

    return ret_url_list[:limit]


def get_tmdb_search_data(title, mediatype):
    url = 'https://api.themoviedb.org/3/search/' + mediatype \
        + '?api_key=' + tmdb_api_key + '&query=' \
        + quote(title.encode('utf-8')) \
        + '&language=en-US&page=1&include_adult=false'
    log.debug('url: %s', url)
    response = retrieve_web_page(url, 'tmdb movie search page')
    if response is None:
        return None
    data = json.loads(response.read().decode('utf-8'))
    response.close()

    return data


class ExtraFinder:

    conn_errors = 0

    def __init__(self, directory, extra_config):

        self.directory = directory
        self.config = extra_config
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
                            youtube_info = ydl.extract_info(url, download=False)
                            break
                    except yt_dlp.DownloadError as e:
                        if 'ERROR: Unable to download webpage:' \
                                in e.args[0]:
                            if tries > 3:
                                log.error('hey, there: error!!!')
                                raise
                            log.error('failed to get video data, retrying')
                            time.sleep(1)

                return youtube_info

            youtube_video = get_video_data()

            if not youtube_video:
                return None

            youtube_video['title'] = \
                get_clean_string(youtube_video['title'])

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

            if youtube_video['width'] is None or youtube_video['height'
                                                               ] is None:
                youtube_video['resolution_ratio'] = 1
                youtube_video['resolution'] = 144
            else:
                youtube_video['resolution_ratio'] = \
                    youtube_video['width'] / youtube_video['height']

                resolution = max(int(youtube_video['height']),
                                 int(youtube_video['width'] / 16 * 9))
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

                youtube_video['resolution'] = \
                    resolutions[bisect(resolutions, resolution * 1.2)
                                - 1]

            if youtube_video['upload_date']:
                if youtube_video['upload_date'] is not None:
                    date_str = youtube_video['upload_date']
                    upload_date = date(int(date_str[:4]),
                                       int(date_str[4:6]), int(date_str[6:8]))
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

        for (search_index, search) in self.config.searches.items():
            query = apply_query_template(search['query'],
                                         self.directory.__dict__)
            limit = int(search['limit'])

            if self.directory.tmdb_id:
                log.debug('tmdb_api_key: %s',
                          str(tmdb_api_key))
                urls = tmdb_search(self.directory.tmdb_id,
                                   self.config.extra_type, 100)
                log.debug('urls= %s', urls)
            else:
                log.error('tmdb_id is missing')
                continue

            if urls:
                url_list += urls

        for url in list(set(url_list)):
            if not any(url in youtube_video['webpage_url']
                       or youtube_video['webpage_url'] in url
                       for youtube_video in self.youtube_videos):
                if 'youtube.com/watch?v=' not in url:
                    continue
                video = create_youtube_video()

                if video:
                    self.youtube_videos.append(video)
                    if not video['categories']:
                        self.play_trailers.append(video)

    def filter_search_result(self):

        filtered_candidates = []

        for youtube_video in self.youtube_videos:

            info = 'Video "' + youtube_video['webpage_url'] \
                + '" was removed. reasons: '
            append_video = True
            log.info('duration: %s', str(youtube_video['duration']))

            if youtube_video['duration'] >= 200:
                info += 'long video, '
                append_video = False
                continue

            for youtube_id in self.directory.banned_youtube_videos_id:
                if youtube_id == youtube_video['id']:
                    info += 'banned youtube video, '
                    append_video = False
                    break

            try:
                for year in self.directory.banned_years:
                    if str(year) in youtube_video['title'].lower():
                        append_video = False
                        info += 'containing banned year in title, '
                        break
                    if any(str(year) in tag.lower() for tag in
                           youtube_video['tags']):
                        append_video = False
                        info += 'containing banned year in tags, '
                        break
            except TypeError:
                append_video = False
                info += \
                    'unable to confirm year not in (tag:TypeError), '

            buffer = 0
            if len(self.directory.banned_title_keywords) > 3:
                buffer = 1
            if len(self.directory.banned_title_keywords) > 10:
                buffer = 2
            for keyword in self.directory.banned_title_keywords:
                if ' ' + keyword.lower() + ' ' in ' ' \
                        + youtube_video['title'].lower() + ' ':
                    buffer -= 1
                    if buffer < 0:
                        append_video = False
                        info += \
                            'containing banned similar title keywords, '
                        break

            if not any(phrase.lower() in youtube_video['title'].lower()
                       for phrase in self.config.required_phrases):
                append_video = False
                info += 'not containing any required phrase, '

            for phrase in self.config.banned_phrases:
                if phrase.lower() in youtube_video['title'].lower():
                    append_video = False
                    info += 'containing a banned phrase, '
                    break

            for channel in self.config.banned_channels:
                if channel.lower() == youtube_video['uploader'].lower():
                    append_video = False
                    info += 'made by a banned channel, '
                    break

            title_in_video = False
            original_title_in_video = False

            buffer = 0
            if len(self.directory.movie_title_keywords) > 3:
                buffer = 1
            if len(self.directory.movie_title_keywords) > 7:
                buffer = 2

            for keyword in self.directory.movie_title_keywords:
                if ' ' + keyword.lower() + ' ' not in ' ' \
                        + youtube_video['title'].lower() + ' ':
                    buffer -= 1
                    if buffer < 0:
                        break
            else:
                title_in_video = True

            if self.directory.movie_original_title is not None:
                buffer = \
                    int(len(self.directory.movie_original_title_keywords)
                        / 4 + 0.1)

                for keyword in \
                        self.directory.movie_original_title_keywords:
                    if ' ' + keyword.lower() + ' ' not in ' ' \
                            + youtube_video['title'].lower() + ' ':
                        buffer -= 1
                        if buffer < 0:
                            break
                else:
                    original_title_in_video = True

            if append_video:
                filtered_candidates.append(youtube_video)
            else:
                log.info('%s.', info[:-2])

        self.youtube_videos = filtered_candidates

        filtered_candidates = []

        for youtube_video in self.play_trailers:

            info = 'Video "' + youtube_video['webpage_url'] \
                + '" was removed. reasons: '
            append_video = True

            for year in self.directory.banned_years:
                if str(year) in youtube_video['title'].lower():
                    append_video = False
                    info += 'containing banned year in title, '
                    break
                if any(str(year) in tag.lower() for tag in
                       youtube_video['tags']):
                    append_video = False
                    info += 'containing banned year in tags, '
                    break

            buffer = 0
            if len(self.directory.banned_title_keywords) > 3:
                buffer = 1
            if len(self.directory.banned_title_keywords) > 6:
                buffer = 2
            for keyword in self.directory.banned_title_keywords:
                if ' ' + keyword.lower() + ' ' in ' ' \
                        + youtube_video['title'].lower() + ' ':
                    buffer -= 1
                    if buffer < 0:
                        append_video = False
                        info += \
                            'containing banned similar title keywords, '
                        break

            title_in_video = False
            original_title_in_video = False

            buffer = 0
            if len(self.directory.movie_title_keywords) > 3:
                buffer = 1
            if len(self.directory.movie_title_keywords) > 7:
                buffer = 2

            for keyword in self.directory.movie_title_keywords:
                if keyword.lower() not in youtube_video['title'
                                                        ].lower():
                    buffer -= 1
                    if buffer < 0:
                        break
            else:
                title_in_video = True

            if self.directory.movie_original_title is not None:
                buffer = \
                    int(len(self.directory.movie_original_title_keywords)
                        / 4 + 0.1)

                for keyword in \
                        self.directory.movie_original_title_keywords:
                    if keyword.lower() not in youtube_video['title'
                                                            ].lower():
                        buffer -= 1
                        if buffer < 0:
                            break
                else:
                    original_title_in_video = True

            if not original_title_in_video and not title_in_video:
                append_video = False
                info += 'not containing title, '

            if append_video:
                filtered_candidates.append(youtube_video)
            else:
                log.info('%s.', info[:-2])

        self.play_trailers = filtered_candidates

    def apply_custom_filters(self):

        def absolute():

            minimum = filter_args[0] == 'min'
            ret = []

            for youtube_video in filtered_list:
                if minimum:
                    if youtube_video[key] >= limit_value:
                        ret.append(youtube_video)
                else:
                    if youtube_video[key] <= limit_value:
                        ret.append(youtube_video)
            return ret

        def relative():

            minimum = filter_args[0] == 'min'
            ret = []
            max_value = float('-inf')

            for youtube_video in filtered_list:
                video_value = youtube_video[key]
                if video_value > max_value:
                    max_value = video_value

            for youtube_video in filtered_list:
                if minimum:
                    if youtube_video[key] >= max_value * limit_value:
                        ret.append(youtube_video)
                else:
                    if youtube_video[key] <= max_value * limit_value:
                        ret.append(youtube_video)
            return ret

        def highest():
            keep = filter_args[0] == 'keep'

            ret = sorted(filtered_list, key=lambda x: x[key],
                         reverse=True)

            if keep:
                if len(ret) > limit_value:
                    ret = ret[:limit_value]
            else:
                if len(ret) > limit_value:
                    ret = ret[limit_value:]
                else:
                    ret = []

            return ret

        def lowest():
            keep = filter_args[0] == 'keep'

            ret = sorted(filtered_list, key=lambda x: x[key])

            if keep:
                if len(ret) > limit_value:
                    ret = ret[:limit_value]
            else:
                if len(ret) > limit_value:
                    ret = ret[limit_value:]
                else:
                    ret = []

            return ret

        filtered_list = None

        for filter_package in self.config.custom_filters:

            filtered_list = list(self.youtube_videos)

            for data in filter_package:
                filter_args = data.split(':::')[0].split('_')
                limit_value = float(data.split(':::')[1])
                try:
                    int(filter_args[-1])
                except ValueError:
                    key = '_'.join(filter_args[2:])
                else:
                    key = '_'.join(filter_args[2:-1])

                if filter_args[1] == 'relative':
                    filtered_list = relative()
                if filter_args[1] == 'absolute':
                    filtered_list = absolute()
                if filter_args[1] == 'highest':
                    filtered_list = highest()
                if filter_args[1] == 'lowest':
                    filtered_list = lowest()
            if self.play_trailers and self.config.extra_type \
                    == 'trailers':
                if len(filtered_list) + 1 >= self.config.break_limit:
                    break
            else:
                if len(filtered_list) >= self.config.break_limit:
                    break

        self.youtube_videos = filtered_list

    def order_results(self):

        attribute_tuple = self.config.priority_order.split('_')
        highest = attribute_tuple[0] == 'highest'
        key = '_'.join(attribute_tuple[1:])

        for youtube_video in self.youtube_videos:
            if youtube_video[key] is None:
                youtube_video[key] = 0

        if highest:
            self.youtube_videos = sorted(self.youtube_videos,
                                         key=lambda x: x[key], reverse=True)
        else:
            self.youtube_videos = sorted(self.youtube_videos,
                                         key=lambda x: x[key])

        preferred_videos = []
        not_preferred_channels = []

        for youtube_video in self.youtube_videos:
            if youtube_video['uploader'] \
                    in self.config.preferred_channels:
                preferred_videos.append(youtube_video)
            else:
                not_preferred_channels.append(youtube_video)

        self.youtube_videos = preferred_videos + not_preferred_channels

        self.play_trailers = sorted(self.play_trailers, key=lambda x:
                                    x['view_count'], reverse=True)

    def download_videos(self, tmp_file):

        downloaded_videos_meta = []

        arguments = self.config.youtube_dl_arguments
        arguments['writesubtitles'] = True
        arguments['quiet'] = True
        arguments['noprogress'] = True
        arguments['subtitle'] = '--write-sub --sub-lang en --write-auto-sub --sub-format srt'
        arguments['logger'] = log
        arguments['outtmpl'] = os.path.join(tmp_file, arguments['outtmpl'])
        log.debug('arguments: %s', arguments)
        for (key, value) in arguments.items():
            if isinstance(value, str):
                if value.lower() == 'false' or value.lower() == 'no':
                    arguments[key] = ''

        count = 0

        for youtube_video in self.youtube_videos[:]:
            if not self.config.force:
                for vid_id in self.directory.record:
                    if vid_id == youtube_video['id']:
                        continue

            for tries in range(1, 11):
                try:
                    with yt_dlp.YoutubeDL(arguments) as ydl:
                        meta = ydl.extract_info(youtube_video['webpage_url'])
                        downloaded_videos_meta.append(meta)
                        count += 1
                        break
                except yt_dlp.DownloadError as e:

                    if tries > 3:
                        if str(e).startswith(
                                'ERROR: Did not get any data blocks'):
                            return None
                        log.error('failed to download the video.')
                        break
                    log.error('failed to download the video. retrying')
                    time.sleep(3)

            if count >= self.config.videos_to_download:
                break

        return downloaded_videos_meta

    def move_videos(self, downloaded_videos_meta, tmp_folder):

        def copy_file():
            if not os.path.isdir(os.path.split(target_path)[0]):
                os.mkdir(os.path.split(target_path)[0])
            shutil.move(source_path, target_path)

        def record_file():
            vid_id = 'unknown'
            for meta in downloaded_videos_meta:
                if meta['title'] + '.' + meta['ext'] == file:
                    vid_id = meta['id']
                    break

            self.directory.record.append({
                'hash': file_hash,
                'file_path': os.path.join(self.directory.full_path,
                                          self.config.extra_type, file),
                'file_name': file,
                'youtube_video_id': vid_id,
                'config_type': self.config.extra_type,
            })

        def determine_case():
            for (content_file, content_file_hash) in \
                    self.directory.content.items():
                if content_file == file:
                    return 'name_in_directory'

                if file_hash == content_file_hash:
                    return 'hash_in_directory'

            for sub_content in self.directory.subdirectories.values():
                for (content_file, content_file_hash) in \
                        sub_content.items():
                    if content_file == file:
                        return 'name_in_directory'
                    if file_hash == content_file_hash:
                        return 'hash_in_directory'

            return ''

        def handle_name_in_directory():
            if self.config.force:
                copy_file()
                record_file()
                self.directory.subdirectories[self.config.extra_type][file] = \
                    file_hash
            else:
                os.remove(source_path)

        def handle_hash_in_directory():
            if self.config.force:
                copy_file()
                record_file()
                if self.config.extra_type \
                        in self.directory.subdirectories:
                    self.directory.subdirectories[self.config.extra_type] = \
                        {file: file_hash}
                else:
                    self.directory.subdirectories = \
                        {self.config.extra_type: {file: file_hash}}
            else:
                os.remove(source_path)

        for file in os.listdir(tmp_folder):
            source_path = os.path.join(tmp_folder, file)
            if self.config.extra_type == 'theme-music':
                target_path = os.path.join(self.directory.full_path,
                                           'theme.mp3')
            else:
                target_path = os.path.join(self.directory.full_path,
                                           self.config.extra_type, file)

            file_hash = hash_file(source_path)

            if any(file_hash == record['hash'] for record in
                   self.directory.record):
                os.remove(source_path)
                continue

            case = determine_case()

            if case == 'name_in_directory':
                handle_name_in_directory()
            elif case == 'hash_in_directory':
                handle_hash_in_directory()
            else:
                copy_file()

                if self.config.extra_type \
                        in self.directory.subdirectories:

                    self.directory.subdirectories[self.config.extra_type][file] = \
                        file_hash
                else:
                    self.directory.subdirectories = \
                        {self.config.extra_type: {file: file_hash}}

                record_file()


class ExtraSettings:

    def __init__(self, config_path):

        with codecs.open(config_path, 'r') as file:
            self.config = configparser.RawConfigParser()
            self.config.read_file(file)

        self.extra_type = self.config['EXTRA_CONFIG'].get('extra_type')
        self.config_id = self.config['EXTRA_CONFIG'].get('config_id')
        self.force = self.config['EXTRA_CONFIG'].getboolean('force')

        self.searches = self.get_searches()

        self.required_phrases = make_list_from_string(
            self.config['FILTERING'].get('required_phrases').replace('\n', ''))
        self.banned_phrases = make_list_from_string(
            self.config['FILTERING'].get('banned_phrases').replace('\n', ''))
        self.banned_channels = make_list_from_string(
            self.config['FILTERING'].get('banned_channels').replace('\n', ''))

        self.custom_filters = self.get_custom_filters()
        self.last_resort_policy = \
            self.config['DOWNLOADING_AND_POSTPROCESSING'
                        ].get('last_resort_policy')

        self.priority_order = self.config['PRIORITY_RULES'].get('order')
        self.preferred_channels = make_list_from_string(
            self.config['PRIORITY_RULES'].get(
                'preferred_channels', '').replace(
                '\n', ''))

        self.videos_to_download = \
            self.config['DOWNLOADING_AND_POSTPROCESSING'
                        ].getint('videos_to_download', 1)
        self.naming_scheme = \
            self.config['DOWNLOADING_AND_POSTPROCESSING'
                        ].get('naming_scheme')
        self.youtube_dl_arguments = \
            json.loads(self.config['DOWNLOADING_AND_POSTPROCESSING'
                                   ].get('youtube_dl_arguments'))

        self.disable_play_trailers = self.config['EXTRA_CONFIG'].getboolean(
            'disable_play_trailers', False)
        self.only_play_trailers = self.config['EXTRA_CONFIG'].getboolean(
            'only_play_trailers', False)
        self.skip_movies_with_existing_trailers = \
            self.config['EXTRA_CONFIG'
                        ].getboolean('skip_movies_with_existing_trailers', False)

        self.skip_movies_with_existing_theme = \
            self.config['EXTRA_CONFIG'
                        ].getboolean('skip_movies_with_existing_theme',
                                     False)

    def get_searches(self):

        ret = {}

        for (option, value) in self.config['SEARCHES'].items():

            try:
                index = int(option.split('_')[-1])
            except ValueError:
                continue

            if index not in ret:
                ret[index] = {}
            ret[index]['_'.join(option.split('_')[:-1])] = value

        return ret

    def get_custom_filters(self):

        ret = {}

        for (option, value) in self.config['CUSTOM_FILTERS'].items():

            if option == 'break_limit':
                self.break_limit = int(value)
                continue
            if option == 'last_resort_policy':
                self.last_resort_policy = value
                continue

            try:
                index = int(option.split('_')[0])
            except ValueError:
                continue

            if index not in ret:
                ret[index] = []
            try:
                ret[index].append('_'.join(option.split('_')[1:])
                                  + ':::' + value)
            except ValueError:
                continue

        sorted_ret = []
        for key in sorted(ret.keys()):
            sorted_ret.append(ret[key])

        return sorted_ret


def download_extra(directory, config, tmp_folder):

    def process(tmp_folder, extra_type):
        finder = ExtraFinder(directory, config)
        log.info('processing: %s', directory.name)
        finder.search()
        finder.filter_search_result()

        for youtube_video in finder.youtube_videos:
            log.info(youtube_video['webpage_url'])
            log.info(str(youtube_video['adjusted_rating']))
            log.info(youtube_video['format'])
            log.info(str(youtube_video['views_per_day']))

        log.info(directory.name)

        finder.apply_custom_filters()
        finder.order_results()

        if finder.play_trailers and finder.youtube_videos \
                and not config.disable_play_trailers:
            if 'duration' in finder.youtube_videos[0] and 'duration' \
                    in finder.play_trailers[0]:
                if finder.youtube_videos[0]['duration'] - 23 \
                    <= finder.play_trailers[0]['duration'] \
                        <= finder.youtube_videos[0]['duration'] + 5:
                    finder.youtube_videos = [finder.play_trailers[0]] \
                        + finder.youtube_videos
                    log.info('picked play trailer.')

        if config.only_play_trailers:
            if finder.play_trailers:
                finder.youtube_videos = [finder.play_trailers[0]]
            else:
                return

        if not finder.youtube_videos and finder.play_trailers \
                and not config.disable_play_trailers:
            finder.youtube_videos = finder.play_trailers

        for youtube_video in finder.youtube_videos:
            log.info('%s : %s (%s)',
                    youtube_video['webpage_url'],
                    youtube_video['format'],
                    str(youtube_video['adjusted_rating']))
        for youtube_video in finder.play_trailers:
            log.info('play trailer: ' + youtube_video['webpage_url']
                     + ' : ' + youtube_video['format'])
        log.info('downloading for: %s', directory.name)
        count = 0
        tmp_folder = os.path.join(tmp_folder, 'tmp_0')
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
        for youtube_id in directory.banned_youtube_videos_id:
            for youtube_video in finder.youtube_videos:
                if youtube_id == youtube_video['id']:
                    finder.youtube_videos.remove(youtube_video)

        downloaded_videos_meta = finder.download_videos(tmp_folder)
        if downloaded_videos_meta:
            finder.move_videos(downloaded_videos_meta, tmp_folder)
            if extra_type in config.extra_type.lower():
                directory.trailer_youtube_video_id = \
                    downloaded_videos_meta[0]['id']

    if config.extra_type.lower() == 'trailers':
        process(tmp_folder, 'trailers')
    elif config.extra_type.lower() == 'behind the scenes':
        process(tmp_folder, 'behind the scenes')
    elif config.extra_type.lower() == 'featurettes':
        process(tmp_folder, 'featurettes')
    elif config.extra_type.lower() == 'scenes':
        process(tmp_folder, 'scenes')


class Directory:

    def __init__(
            self,
            full_path,
            tmdb_id=None,
            json_dict=None,):

        # #######################################

        self.name = None
        self.full_path = None
        self.content = dict
        self.subdirectories = {}

        self.tmdb_id = None
        self.movie_title = None
        self.movie_original_title = None
        self.movie_original_title_keywords = None
        self.movie_release_year = None
        self.movie_title_keywords = []
        self.movie_crew_data = []
        self.trailer_youtube_video_id = None

        self.banned_title_keywords = []
        self.banned_years = []
        self.banned_youtube_videos_id = []

        self.record = []
        self.completed_configs = []

        # #######################################

        if full_path is None:
            for (key, value) in json_dict.items():
                setattr(self, key, value)
        else:
            self.update_all(full_path=full_path,
                            tmdb_id=tmdb_id)

    @classmethod
    def load_directory(cls, file):
        with open(file, 'r', 'utf-8') as load_file:
            return Directory(None, json_dict=json.load(load_file))

    def update_all(
            self,
            full_path=None,
            tmdb_id=None):

        if full_path is not None:
            self.name = os.path.split(full_path)[1]
            self.full_path = full_path
        self.update_content()
        self.update_movie_info(tmdb_id=tmdb_id)
        if tmdb_api_key is not None:
            self.update_similar_results()

    def update_content(self):

        self.content = {}
        self.subdirectories = {}

        for file in os.listdir(self.full_path):
            if os.path.isdir(os.path.join(self.full_path, file)):
                sub_content = {}
                for sub_file in os.listdir(os.path.join(self.full_path,
                                                        file)):
                    sub_content[sub_file] = \
                        hash_file(os.path.join(self.full_path, file,
                                  sub_file))
                self.subdirectories[file] = sub_content
            else:
                self.content[file] = \
                    hash_file(os.path.join(self.full_path, file))

    def update_movie_info(
            self,
            tmdb_id=None):

        def get_info_from_directory():
            clean_name_tuple = get_clean_string(self.name).split(' ')

            if any(clean_name_tuple[-1] == str(year) for year in
                   range(1896, date.today().year + 2)):
                self.movie_release_year = int(clean_name_tuple[-1])
                self.movie_title = ' '.join(clean_name_tuple[:-1])
                self.movie_original_title = \
                    ' '.join(clean_name_tuple[:-1])
            else:

                self.movie_release_year = None
                self.movie_title = ' '.join(clean_name_tuple)
                self.movie_original_title = ' '.join(clean_name_tuple)

            self.movie_title_keywords = \
                get_keyword_list(self.movie_title)
            self.movie_original_title_keywords = \
                get_keyword_list(self.movie_original_title)

            return True

        def get_tmdb_details_data(tmdb_id):
            url = 'https://api.themoviedb.org/3/' + args.mediatype + '/' + str(tmdb_id) + \
                                            '?api_key=' + tmdb_api_key + \
                                            '&language=en-US'
            log.debug('url: %s', url)
            response = retrieve_web_page(url, 'movie details')
            if response is None:
                return None
            data = json.loads(response.read().decode('utf-8'))
            response.close()

            return data

        def get_info_from_details():
            details_data = get_tmdb_details_data(tmdb_id)
            log.debug('details_data: %s', str(details_data))
            if details_data is not None:
                try:
                    self.tmdb_id = details_data['id']
                    self.movie_title = details_data['title']
                    self.movie_original_title = \
                        details_data['original_title']
                    self.movie_title_keywords = \
                        get_keyword_list(details_data['title'])
                    self.movie_original_title_keywords = \
                        get_keyword_list(details_data['original_title'])

                    if len((details_data['release_date'])[:4]) == 4:
                        self.movie_release_year = \
                            int((details_data['release_date'])[:4])
                    else:
                        self.movie_release_year = None
                    return True
                except KeyError as ke:
                    return False
                except TypeError as te:
                    return False
            else:
                return False

        def get_info_from_search():
            search_data = get_tmdb_search_data(self.movie_title, args.mediatype)

            if search_data is None or search_data['total_results'] == 0:
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
                        if str(self.movie_release_year) \
                                == (data['release_date'])[:4]:
                            movie_data = data
                        elif (data['release_date'])[6:8] in ['09',
                                                               '10', '11', '12'] \
                                and str(self.movie_release_year - 1) \
                                == (data['release_date'])[:4]:

                            movie_data = data
                        elif (data['release_date'])[6:8] in ['01',
                                                               '02', '03', '04'] \
                                and str(self.movie_release_year + 1) \
                                == (data['release_date'])[:4]:

                            movie_data = data
                    elif movie_backup_data is None:
                        if str(self.movie_release_year - 1) \
                                == (data['release_date'])[:4]:
                            movie_backup_data = data
                        elif str(self.movie_release_year + 1) \
                                == (data['release_date'])[:4]:

                            movie_backup_data = data

                if movie_data is None and movie_backup_data is not None:
                    log.info( 'None of the search results had a correct release year, picking the next best result')
                    movie_data = movie_backup_data

                if movie_data is None:
                    movie_data = search_data['results'][0]

            self.tmdb_id = movie_data['id']
            if args.mediatype == 'movie':
                self.movie_title = get_clean_string(movie_data['title'])
                self.movie_original_title = \
                    get_clean_string(movie_data['original_title'])
                self.movie_title_keywords = \
                    get_keyword_list(movie_data['title'])
                self.movie_original_title_keywords = \
                    get_keyword_list(movie_data['original_title'])
                if len((movie_data['release_date'])[:4]) == 4:
                    self.movie_release_year = \
                        int((movie_data['release_date'])[:4])
                else:
                    self.movie_release_year = None
            else:
                self.movie_title = get_clean_string(movie_data['name'])
                self.movie_original_title = \
                    get_clean_string(movie_data['original_name'])
                self.movie_title_keywords = \
                    get_keyword_list(movie_data['name'])
                if len((movie_data['first_air_date'])[:4]) == 4:
                    self.movie_release_year = \
                        int((movie_data['first_air_date'])[:4])
                else:
                    self.movie_release_year = None
            return True

        if tmdb_api_key is not None:
            if tmdb_id is not None:
                if get_info_from_details():
                    return True
            if get_info_from_directory():
                if get_info_from_search():
                    return True
            else:
                return False

        return get_info_from_directory()

    def update_similar_results(self):

        def find_similar_results():

            def find_by_tmdb_id():
                similar_movies_data = []
                for data in search_data['results']:
                    if self.tmdb_id != data['id']:
                        similar_movies_data.append(data)
                return similar_movies_data

            def find_by_release_year():
                similar_movies_data = []
                movie_found = False
                backup_found = False
                result = None

                for data in search_data['results']:
                    log.info('find_by_release_year: release_date=%s', data['release_date'])

                    if not movie_found and str(self.movie_release_year) \
                            == (data['release_date'])[:4]:
                        movie_found = True
                        continue

                    if not backup_found:
                        if data['release_date'][6:8] in ['09', '10', '11', '12'] \
                                and str(self.movie_release_year - 1) == data['release_date'][:4]:
                            backup_found = True
                        elif data['release_date'][6:8] in ['01', '02', '03'] \
                                and str(self.movie_release_year + 1) == data['release_date'][:4]:
                            backup_found = True

                    if len(similar_movies_data) < 5:
                        similar_movies_data.append(data)

                if movie_found or backup_found:
                    result = similar_movies_data
                return result

            search_data = get_tmdb_search_data(self.movie_title, args.mediatype)

            if search_data is None or search_data['total_results'] == 0:
                return []

            ret = find_by_tmdb_id()
            if ret is not None:
                return ret[:5]

            if self.movie_release_year is None:
                return (search_data['results'])[1:6]

            ret = find_by_release_year()
            if ret is not None:
                return ret[:5]

            return None

        def process_similar_results():
            self.banned_title_keywords = []
            self.banned_years = []

            for similar_movie in similar_movies:

                if args.mediatype == 'movie':
                    for word in get_keyword_list(similar_movie['title'
                                                               ]):

                        if word.lower() not in self.movie_title.lower() \
                                and word.lower() \
                                not in self.banned_title_keywords:

                            if self.movie_original_title is not None:

                                if word.lower() \
                                        not in self.movie_original_title.lower():
                                    self.banned_title_keywords.append(word)
                            else:

                                self.banned_title_keywords.append(word)
                    try:
                        if len((similar_movie['release_date'])[:4]) \
                            == 4 and int((similar_movie['release_date'
                                                        ])[:4]) \
                            not in [self.movie_release_year] \
                            + self.banned_years \
                            and (similar_movie['release_date'])[:4] \
                                not in self.movie_title:

                            self.banned_years.append(
                                int((similar_movie['release_date'])[:4]))
                    except KeyError as e:
                        pass

        similar_movies = find_similar_results()
        if similar_movies is not None:
            process_similar_results()
            return True

    def save_directory(self, save_path):
        self.content = None
        self.subdirectories = None
        if not os.path.isdir(save_path):
            os.mkdir(os.path.join(save_path))
        with open(os.path.join(save_path, self.name), 'w') as save_file:
            json.dump(self.__dict__, save_file)


def handle_directory(folder):
    log.info('working on directory: " %s', folder + '"')
    for config in configs_content:

        if config.startswith('.') or config.startswith('_'):
            continue
        try:
            try:
                if not args.force:
                    directory = Directory.load_directory(
                        os.path.join(records, os.path.split(folder)[1]))
                else:
                    if has_tmdb_key:
                        directory = Directory(folder,
                                              tmdb_id=args.tmdbid)
                    else:
                        directory = Directory(folder)
            except FileNotFoundError:
                if has_tmdb_key:
                    directory = Directory(folder,
                                          tmdb_id=args.tmdbid)
                else:
                    directory = Directory(folder)

            extra_config = ExtraSettings(os.path.join(extra_configs_directory,
                                                      config))

            if args.replace and 'trailer' in extra_config.extra_type.lower():
                args.force = True

            if extra_config.config_id in directory.completed_configs \
                    and not args.force:
                continue

            if extra_config.skip_movies_with_existing_trailers \
                    and not args.replace:
                skip = False
                for file in os.listdir(directory.full_path):
                    if file.lower().endswith('trailer.mp4') \
                            or file.lower().endswith('trailer.mkv'):
                        skip = True
                        break
                if skip:
                    log.info('movie already have a trailer. skipping.')
                    directory.save_directory(records)
                    continue
                if os.path.isdir(os.path.join(directory.full_path,
                                 'trailers')):
                    for file in \
                        os.listdir(os.path.join(directory.full_path,
                                   'trailers')):
                        if file.lower().endswith('.mp4') \
                                or file.lower().endswith('.mkv'):
                            skip = True
                            break
                    if skip:
                        log.info('movie already have a trailer. skipping.')
                        directory.save_directory(records)
                        continue

            if extra_config.skip_movies_with_existing_theme:
                skip = False
                for file in os.listdir(directory.full_path):
                    if file.lower().endswith('theme.mp3') \
                            or file.lower().endswith('theme.wma') \
                            or file.lower().endswith('theme.flac'):
                        skip = True
                        break
                if skip:
                    log.info('movie already have a theme song. skipping.')
                    directory.save_directory(records)
                    continue
                if os.path.isdir(os.path.join(directory.full_path,
                                 'theme-music')):
                    for file in \
                        os.listdir(os.path.join(directory.full_path,
                                   'theme-music')):
                        if file.lower().endswith('.mp3') \
                                or file.lower().endswith('.wma') \
                                or file.lower().endswith('.flac'):
                            skip = True
                            break
                    if skip:
                        log.info('movie already have a theme song. skipping.')
                        directory.save_directory(records)
                        continue

            directory.update_content()

            if args.force:
                old_record = directory.record
                directory.record = []
                for record in old_record:
                    if record != extra_config.extra_type:
                        directory.record.append(record)
                extra_config.force = True

            if args.replace:
                directory.banned_youtube_videos_id.append(
                    directory.trailer_youtube_video_id)
                shutil.rmtree(os.path.join(directory.full_path,
                              extra_config.extra_type),
                              ignore_errors=True)
                os.mkdir(os.path.join(directory.full_path,
                         extra_config.extra_type))

            if not os.path.isdir(tmp_folder):
                os.mkdir(tmp_folder)

            download_extra(directory, extra_config, tmp_folder)
            directory.completed_configs.append(extra_config.config_id)
            directory.save_directory(records)

            if args.force:
                log.debug('record: %s', str(directory.record))

        except FileNotFoundError as e:

            log.error('file not found: %s', str(e))
            continue
        except HTTPError:

            log.error(
                'You might have been flagged by google search. try again tomorrow.')
            sys.exit()
        except URLError:

            log.error('you might have lost your internet connections. exiting')
            sys.exit()
        except timeout:

            log.error('you might have lost your internet connections. exiting')
            sys.exit()
        except ConnectionResetError:

            log.error('you might have lost your internet connections. exiting')
            sys.exit()
        except KeyboardInterrupt:

            log.error('exiting! keyboard interrupt.')
            sys.exit()


def handle_library(library):
    if args.replace:
        log.error(
            'the replace mode is unable in library mode, please use the directory mode.')
        return False
    for folder in os.listdir(library):
        if folder.startswith('.'):
            continue
        if not os.path.isdir(os.path.join(library, folder)):
            continue
        try:
            handle_directory(os.path.join(library, folder))
        except KeyboardInterrupt:
            raise
        except Exception as e:

            log.error(
                '--------------------AN ERROR OCCURRED---------------------')
            log.error(
                '------------------------SKIPPING--------------------------')
            log.error(
                '------PLEASE REPORT MOVIE TITLE TO THE GITHUB ISSUES------')
            log.error(
                '-----------------THE SCRIPT WILL CONTINUE-----------------')
            log.error(
                '-------------------- Exception: --------------------------')
            log.error(e)
            log.error(traceback.format_exc())
            time.sleep(1)
            sys.exit(1)

    return True


default_config = configparser.ConfigParser()
default_config.read(os.path.join(os.path.dirname(sys.argv[0]),
                    'default_config.cfg'))

tmp_folder = os.path.join(os.path.dirname(sys.argv[0]), 'tmp')

extra_configs_directory = os.path.join(os.path.dirname(sys.argv[0]),
                                       'extra_configs')
configs_content = os.listdir(extra_configs_directory)

records = os.path.join(os.path.dirname(sys.argv[0]), 'records')

tmdb_api_key = default_config.get('SETTINGS', 'tmdb_api_key')
result = get_tmdb_search_data('star wars', 'movie')
if result is None:
    log.error('Warning: No working TMDB api key was specified.')
    time.sleep(10)
    has_tmdb_key = False
else:
    has_tmdb_key = True

if not args.mediatype:
    log.error('please specify media type (-m) to search extras for')
    sys.exit(1)

if args.directory:
    handle_directory(args.directory)
elif args.library:
    handle_library(args.library)
else:
    log.error(
        'please specify a directory (-d) or a library (-l) to search extras for')

try:
    shutil.rmtree(tmp_folder, ignore_errors=True)
except FileNotFoundError:
    pass
os.mkdir(tmp_folder)

sys.exit()