from googlesearch import search as google_web_search
from time import sleep
from time import time
import os, sys, logging

from urllib.error import HTTPError

import tools, json
from bs4 import BeautifulSoup
from urllib.parse import quote

last = None

log = logging.getLogger("med")

def google_search(query, limit):
    global last
    ret_url_list = list()

    for tries in range(1, 10):
        try:
            if last:
                sleep(int(60 - (time() - last)))
        except ValueError:
            pass

        last = time()

        try:
            for url in google_web_search(query, stop=limit):
                if 'youtube.com/watch?v=' in url:
                    ret_url_list.append(url.split('&')[0])

        except KeyboardInterrupt:
            raise

        except HTTPError as e:
            log.error('google search service unavailable.')

            if tries > 3:
                log.error('Failed to download google search result. Reason: ' + str(e))
                raise

            log.error('Failed to download google search result, retrying. Reason: ' + str(e))
            sleep(1)

        except:
            e = sys.exc_info()[0]
            if tries > 3:
                log.error('Failed to download google search result. Reason: ' + str(e))
                raise

            log.error('Failed to download google search result, retrying. Reason: ' + str(e))
            sleep(1)
        else:
            break

    return ret_url_list[:limit]


def youtube_search(query, limit):
    ret_url_list = list()
    for tries in range(1, 10):
        try:
            response = tools.retrieve_web_page('https://www.youtube.com/results?search_query=' +
                                               quote(query.encode('utf-8')),
                                               'youtube search result')
        except KeyboardInterrupt:
            raise
        except:
            e = sys.exc_info()[0]
            if tries > 3:
                log.error('Failed to download google search result. Reason: ' + str(e))
                raise
            log.error('Failed to download google search result, retrying. Reason: ' + str(e))
            sleep(1)
        else:
            if response:
                soup = BeautifulSoup(response, "html.parser")
                for item in soup.findAll(attrs={'class': 'yt-uix-tile-link'}):
                    url = 'https://www.youtube.com' + item['href']
                    ret_url_list.append(url.split('&')[0])
            break
    return ret_url_list[:limit]

def youtube_channel_search(query, limit):
    # todo (1): implement youtube_channel_search.
    pass

def tmdb_search(tmdb_api_key, tmdb_id, limit):
    ret_url_list = list()
    response = tools.retrieve_web_page('https://api.themoviedb.org/3/movie/'
                                       + str(tmdb_id) +
                                       '/videos?api_key=' + tmdb_api_key +
                                       '&language=en-US', 'tmdb movie videos')
    if response is None:
        return None
    data = json.loads(response.read().decode('utf-8'))
    response.close()

    for result in data['results']:
        if result['type'] == 'Trailer' or result['type'] == 'Teaser':
            url = 'https://www.youtube.com/watch?v=' + result['key']
            ret_url_list.append(url)

    return ret_url_list[:limit]
