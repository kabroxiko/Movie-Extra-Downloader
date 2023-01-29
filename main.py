import os, sys, logging

from extra_finder import ExtraFinder

log = logging.getLogger("med")

def download_extra(directory, config, tmp_folder):
    def process(tmp_folder, extra_type):
        finder = ExtraFinder(directory, config)
        log.info('processing: ' + directory.name)
        finder.search()
        finder.filter_search_result()

        for youtube_video in finder.youtube_videos:
            log.info('--------------------------------------------------------------------------------------')
            log.info(youtube_video['webpage_url'])
            log.info(str(youtube_video['adjusted_rating']))
            log.info(youtube_video['format'])
            log.info(str(youtube_video['views_per_day']))
        log.info('--------------------------------------------------------------------------------------')
        log.info(directory.name)

        finder.apply_custom_filters()
        finder.order_results()

        if finder.play_trailers and finder.youtube_videos and not config.disable_play_trailers:
            if 'duration' in finder.youtube_videos[0] and 'duration' in finder.play_trailers[0]:
                if finder.youtube_videos[0]['duration'] - 23 <= \
                        finder.play_trailers[0]['duration'] <= \
                        finder.youtube_videos[0]['duration'] + 5:
                    finder.youtube_videos = [finder.play_trailers[0]] + finder.youtube_videos
                    log.info('picked play trailer.')

        if config.only_play_trailers:
            if finder.play_trailers:
                finder.youtube_videos = [finder.play_trailers[0]]
            else:
                return

        if not finder.youtube_videos and finder.play_trailers and not config.disable_play_trailers:
            finder.youtube_videos = finder.play_trailers

        for youtube_video in finder.youtube_videos:
            log.info(youtube_video['webpage_url'] + ' : ' +
                  youtube_video['format'] +
                  ' (' + str(youtube_video['adjusted_rating']) + ')')
        for youtube_video in finder.play_trailers:
            log.info('play trailer: ' + youtube_video['webpage_url'] + ' : ' + youtube_video['format'])
        log.info('--------------------------------------------------------------------------------------')
        log.info('downloading for: ' + directory.name)
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
                directory.trailer_youtube_video_id = downloaded_videos_meta[0]['id']

    if config.extra_type.lower() == 'trailers':
        process(tmp_folder, 'trailers')
    elif config.extra_type.lower() == 'behind the scenes':
        process(tmp_folder, 'behind the scenes')
    elif config.extra_type.lower() == 'featurettes':
        process(tmp_folder, 'featurettes')
    elif config.extra_type.lower() == 'scenes':
        process(tmp_folder, 'scenes')
