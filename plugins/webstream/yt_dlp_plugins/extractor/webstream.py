"""Extend GenericIE only after native extraction reports UnsupportedError."""
from urllib.parse import urlsplit

from yt_dlp.extractor.generic import GenericIE
from yt_dlp.utils import UnsupportedError, ExtractorError, determine_ext
from ._webstream_parser import Page, discover

__all__ = []  # Override GenericIE; do not register a catch-all ahead of native IEs.


class WebStreamFallbackIE(GenericIE, plugin_name='webstream_fallback'):
    def _stream_candidates(self, page, video_id):
        tested = set()
        for candidate in discover(page):
            tested.add(candidate[0])
            yield candidate
        # Run this second stage even when inline strings were found but invalid.
        scripts = []
        for script in [s for s in page.external if urlsplit(s).netloc == urlsplit(page.url).netloc][:4]:
            body = self._download_webpage(script, video_id, note='Reading external player configuration',
                                          fatal=False, headers={'Referer': page.url})
            if body:
                scripts.append(body[:500000])
        if scripts:
            for candidate in discover(page, scripts):
                if candidate[0] not in tested:
                    yield candidate

    def _real_extract(self, url):
        try:
            return super()._real_extract(url)
        except UnsupportedError:
            self.to_screen('Native extractor found no video; trying webpage stream fallback')
        queue, seen, attempts = [(url, url, 0)], set(), 0
        video_id = self._generic_id(url)
        while queue and len(seen) < 6:
            current, referer, depth = queue.pop(0)
            if current in seen or urlsplit(current).scheme not in ('https', 'http'):
                continue
            seen.add(current)
            page_text = self._download_webpage(current, video_id, note='Reading player configuration',
                                               fatal=False, headers={'Referer': referer})
            if not page_text:
                continue
            page = Page(page_text, current)
            for media, score in self._stream_candidates(page, video_id):
                attempts += 1
                if attempts > 24:
                    break
                headers = {'Referer': current}
                ext = determine_ext(media)
                formats, subtitles = [], {}
                if ext == 'm3u8':
                    formats, subtitles = self._extract_m3u8_formats_and_subtitles(
                        media, video_id, 'mp4', entry_protocol='m3u8_native', m3u8_id='hls', fatal=False, headers=headers)
                elif ext == 'mpd':
                    formats, subtitles = self._extract_mpd_formats_and_subtitles(
                        media, video_id, mpd_id='dash', fatal=False, headers=headers)
                else:
                    # Let the native direct-media extractor validate and inspect MP4/WebM.
                    response = self._request_webpage(media, video_id, note='Checking direct media',
                                                      fatal=False, headers={**headers, 'Range': 'bytes=0-0'})
                    if response:
                        content_type = response.headers.get('Content-Type', '').lower()
                        response.close()
                        if content_type.startswith(('video/', 'audio/')) or 'octet-stream' in content_type:
                            formats = [{'url': media, 'format_id': 'http', 'ext': ext}]
                if not formats:
                    continue
                for fmt in formats:
                    fmt['http_headers'] = {**headers, **fmt.get('http_headers', {})}
                self.to_screen('Webpage fallback resolved a video stream; downloading with normal quality settings')
                return {
                    'id': video_id, 'title': self._html_extract_title(page_text, default=None) or 'video-' + video_id,
                    'formats': formats, 'subtitles': subtitles, 'http_headers': headers,
                    'webpage_url': url, 'original_url': url,
                }
            if depth < 2:
                queue.extend((frame, current, depth + 1) for frame in page.frames[:4] if frame not in seen)
        raise ExtractorError('Webpage fallback found no usable public video stream. The page may need login, '
                             'a browser-only API, or an unsupported player. DRM is not supported.', expected=True)
