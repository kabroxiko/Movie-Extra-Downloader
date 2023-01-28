#!/usr/bin/python3

import traceback

from main import download_extra
from extra_config import ExtraSettings
import os, logging
import sys
from directory import Directory
import shutil
from urllib.error import URLError, HTTPError
import configparser
from _socket import timeout
import argparse
import tools
import time

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--directory", help="directory to search extras for")
parser.add_argument("-l", "--library", help="library of directories to search extras for")
parser.add_argument("-t", "--tmdbid", help="tmdb id to search extras for")
parser.add_argument("-m", "--mediatype", help="media type to search extras for")
parser.add_argument("-f", "--force", action="store_true", help="force scan the directories")
parser.add_argument("-r", "--replace", action="store_true", help="remove and ban the existing extra")
args = parser.parse_args()

if args.directory and os.path.split(args.directory)[1] == '':
    args.directory = os.path.split(args.directory)[0]

if args.library and os.path.split(args.library)[1] == '':
    args.library = os.path.split(args.library)[0]

# Setup logger
logging.basicConfig(
    level=logging.DEBUG,
    format='%(message)s'
)
log = logging.getLogger("med")

# Retrieve Required Variables
if os.environ.get('sonarr_eventtype') == "Test":
    log.info('Test Sonarr works')
    sys.exit(0)
elif os.environ.get('radarr_eventtype') == "Test":
    log.info('Test Radarr works')
    sys.exit(0)
elif 'sonarr_eventtype' in os.environ:
    args.directory = os.environ.get('sonarr_series_path')
    args.mediatype = 'tv'
    log.info("directory: " + args.directory)
elif 'radarr_eventtype' in os.environ:
    args.directory = os.environ.get('radarr_movie_path')
    args.tmdbid = os.environ.get('radarr_movie_tmdbid')
    args.mediatype = 'movie'
    log.info("directory: " + args.directory)

def handle_directory(folder):
    log.info('working on directory: "' + folder + '"')
    for config in configs_content:

        if config.startswith('.') or config.startswith('_'):
            continue
        try:
            try:
                if args.force != True:
                    directory = Directory.load_directory(os.path.join(records, os.path.split(folder)[1]))
                else:
                    if has_tmdb_key:
                        directory = Directory(folder, tmdb_api_key=tmdb_api_key, tmdb_id=args.tmdbid, media_type=args.mediatype)
                    else:
                        directory = Directory(folder)
            except FileNotFoundError:
                if has_tmdb_key:
                    directory = Directory(folder, tmdb_api_key=tmdb_api_key, tmdb_id=args.tmdbid, media_type=args.mediatype)
                else:
                    directory = Directory(folder)

            extra_config = ExtraSettings(os.path.join(extra_configs_directory, config))

            if args.replace and 'trailer' in extra_config.extra_type.lower():
                args.force = True

            if extra_config.config_id in directory.completed_configs and not args.force:
                continue

            if extra_config.skip_movies_with_existing_trailers and not args.replace:
                skip = False
                for file in os.listdir(directory.full_path):
                    if file.lower().endswith('trailer.mp4')\
                            or file.lower().endswith('trailer.mkv'):
                        skip = True
                        break
                if skip:
                    log.info('movie already have a trailer. skipping.')
                    directory.save_directory(records)
                    continue
                if os.path.isdir(os.path.join(directory.full_path, 'trailers')):
                    for file in os.listdir(os.path.join(directory.full_path, 'trailers')):
                        if file.lower().endswith('.mp4')\
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
                    if file.lower().endswith('theme.mp3')\
                            or file.lower().endswith('theme.wma')\
                            or file.lower().endswith('theme.flac'):
                        skip = True
                        break
                if skip:
                    log.info('movie already have a theme song. skipping.')
                    directory.save_directory(records)
                    continue
                if os.path.isdir(os.path.join(directory.full_path, 'theme-music')):
                    for file in os.listdir(os.path.join(directory.full_path, 'theme-music')):
                        if file.lower().endswith('.mp3')\
                                or file.lower().endswith('.wma')\
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
                directory.record = list()
                for record in old_record:
                    if record != extra_config.extra_type:
                        directory.record.append(record)
                extra_config.force = True

            if args.replace:
                directory.banned_youtube_videos_id.append(directory.trailer_youtube_video_id)
                shutil.rmtree(os.path.join(directory.full_path, extra_config.extra_type), ignore_errors=True)
                os.mkdir(os.path.join(directory.full_path, extra_config.extra_type))

            if not os.path.isdir(tmp_folder):
                os.mkdir(tmp_folder)

            download_extra(directory, extra_config, tmp_folder)
            directory.completed_configs.append(extra_config.config_id)
            directory.save_directory(records)

            if args.force:
                # todo: delete all paths in the old record that are not in the new record
                log.debug("record: " + str(directory.record))
                pass

        except FileNotFoundError as e:
            log.error('file not found: ' + str(e))
            continue

        except HTTPError:
            log.error('You might have been flagged by google search. try again tomorrow.')
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
        log.error('the replace mode is unable in library mode, please use the directory mode.')
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
            log.error("----------------------------------------------------------")
            log.error("----------------------------------------------------------")
            log.error("----------------------------------------------------------")
            log.error("----------------------------------------------------------")
            log.error("----------------------------------------------------------")
            log.error("--------------------AN ERROR OCCURRED---------------------")
            log.error("------------------------SKIPPING--------------------------")
            log.error("------PLEASE REPORT MOVIE TITLE TO THE GITHUB ISSUES------")
            log.error("-----------------THE SCRIPT WILL CONTINUE-----------------")
            log.error("----------------------------------------------------------")
            log.error("-------------------- Exception: --------------------------")
            log.error(e)
            log.error(traceback.format_exc())
            log.error("----------------------------------------------------------")
            log.error("----------------------------------------------------------")
            time.sleep(1)
            exit()

            if not os.path.isdir(os.path.join(os.path.dirname(sys.argv[0]), "failed_movies")):
                os.mkdir(os.path.join(os.path.dirname(sys.argv[0]), "failed_movies"))
            if not os.path.isdir(os.path.join(os.path.dirname(sys.argv[0]), "failed_movies", folder)):
                os.mkdir(os.path.join(os.path.dirname(sys.argv[0]), "failed_movies", folder))
            if library == 'testdir':
                raise
    return True


default_config = configparser.ConfigParser()
default_config.read(os.path.join(os.path.dirname(sys.argv[0]), 'default_config.cfg'))

tmp_folder = os.path.join(os.path.dirname(sys.argv[0]), 'tmp')

extra_configs_directory = os.path.join(os.path.dirname(sys.argv[0]), 'extra_configs')
configs_content = os.listdir(extra_configs_directory)

records = os.path.join(os.path.dirname(sys.argv[0]), 'records')

tmdb_api_key = default_config.get('SETTINGS', 'tmdb_api_key')
result = tools.get_tmdb_search_data(tmdb_api_key, 'movie', 'star wars')
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
    log.error('please specify a directory (-d) or a library (-l) to search extras for')

try:
    shutil.rmtree(tmp_folder, ignore_errors=True)
except FileNotFoundError:
    pass
os.mkdir(tmp_folder)

sys.exit()
