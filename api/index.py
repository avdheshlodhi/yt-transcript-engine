"""
YTTranscript.in
YouTube Transcript API for Vercel Serverless Functions

Endpoint:
    GET /api?url=https://www.youtube.com/watch?v=VIDEO_ID

Examples:
    /api?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ
    /api?url=https://youtu.be/dQw4w9WgXcQ
    /api?url=https://www.youtube.com/shorts/dQw4w9WgXcQ

Response:
{
    "success": true,
    "video_id": "dQw4w9WgXcQ",
    "language": "en",
    "transcript": [
        {
            "timestamp": "00:12",
            "text": "Hello world"
        }
    ]
}

No transcript:
{
    "error": "Subtitles are unavailable for this video."
}
"""


# ================================================================
# STANDARD LIBRARY IMPORTS
# ================================================================

import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote


# ================================================================
# THIRD-PARTY LIBRARY
# ================================================================

from youtube_transcript_api import YouTubeTranscriptApi


# ================================================================
# OPTIONAL EXCEPTION IMPORTS
# ================================================================

# youtube-transcript-api exposes specific exceptions for common
# transcript failures. We import them defensively so the function
# remains compatible with package variations.

try:
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
        CouldNotRetrieveTranscript,
        RequestBlocked,
        IpBlocked,
    )
except ImportError:
    TranscriptsDisabled = Exception
    NoTranscriptFound = Exception
    VideoUnavailable = Exception
    CouldNotRetrieveTranscript = Exception
    RequestBlocked = Exception
    IpBlocked = Exception


# ================================================================
# CONSTANTS
# ================================================================

ERROR_MESSAGE = (
    "Subtitles are unavailable for this video."
)

INVALID_URL_MESSAGE = (
    "Please provide a valid YouTube video URL."
)

METHOD_MESSAGE = (
    "Only GET and OPTIONS requests are allowed."
)

VIDEO_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9_-]{11}$"
)


# ================================================================
# CORS HEADERS
# ================================================================

def add_cors_headers(handler):
    """
    Add CORS headers to every response.

    This is important because your frontend may be hosted on
    yttranscript.in while the API is deployed on another
    Vercel domain.
    """

    handler.send_header(
        "Access-Control-Allow-Origin",
        "*"
    )

    handler.send_header(
        "Access-Control-Allow-Methods",
        "GET, OPTIONS"
    )

    handler.send_header(
        "Access-Control-Allow-Headers",
        "Content-Type"
    )


# ================================================================
# JSON RESPONSE HELPER
# ================================================================

def send_json(handler, payload, status_code=200):
    """
    Send a JSON response with the required CORS headers.
    """

    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":")
    ).encode("utf-8")


    handler.send_response(status_code)

    handler.send_header(
        "Content-Type",
        "application/json; charset=utf-8"
    )

    handler.send_header(
        "Cache-Control",
        "no-store"
    )

    add_cors_headers(handler)

    handler.send_header(
        "Content-Length",
        str(len(body))
    )

    handler.end_headers()

    handler.wfile.write(body)


# ================================================================
# YOUTUBE VIDEO ID EXTRACTION
# ================================================================

def extract_video_id(value):
    """
    Extract an 11-character YouTube video ID from supported URLs.

    Supported:

    1. https://www.youtube.com/watch?v=VIDEO_ID
    2. https://youtube.com/watch?v=VIDEO_ID
    3. https://m.youtube.com/watch?v=VIDEO_ID
    4. https://youtu.be/VIDEO_ID
    5. https://www.youtube.com/shorts/VIDEO_ID
    6. https://www.youtube.com/embed/VIDEO_ID
    7. https://www.youtube.com/live/VIDEO_ID

    The function also accepts a raw 11-character video ID.
    """

    if not value:
        return None


    value = unquote(
        str(value).strip()
    )


    # ------------------------------------------------------------
    # Direct video ID
    # ------------------------------------------------------------

    if VIDEO_ID_PATTERN.fullmatch(value):
        return value


    # ------------------------------------------------------------
    # Add https:// when a user supplies:
    #
    # youtube.com/watch?v=...
    # www.youtube.com/watch?v=...
    # youtu.be/...
    # ------------------------------------------------------------

    normalized = value

    if not re.match(
        r"^[a-zA-Z][a-zA-Z0-9+.-]*://",
        normalized
    ):
        normalized = "https://" + normalized


    try:
        parsed = urlparse(
            normalized
        )

    except Exception:
        return None


    hostname = (
        parsed.hostname or ""
    ).lower()


    hostname = hostname.lstrip(
        "www."
    )


    pathname = parsed.path or ""


    # ------------------------------------------------------------
    # youtube.com / m.youtube.com
    # ------------------------------------------------------------

    if hostname in (
        "youtube.com",
        "m.youtube.com"
    ):

        # Standard watch URL
        if pathname == "/watch":

            query = parse_qs(
                parsed.query
            )

            video_id = query.get(
                "v",
                [None]
            )[0]

            if (
                video_id and
                VIDEO_ID_PATTERN.fullmatch(
                    video_id
                )
            ):
                return video_id


        # Shorts
        match = re.match(
            r"^/shorts/([A-Za-z0-9_-]{11})(?:/|$)",
            pathname
        )

        if match:
            return match.group(1)


        # Embed
        match = re.match(
            r"^/embed/([A-Za-z0-9_-]{11})(?:/|$)",
            pathname
        )

        if match:
            return match.group(1)


        # Live
        match = re.match(
            r"^/live/([A-Za-z0-9_-]{11})(?:/|$)",
            pathname
        )

        if match:
            return match.group(1)


    # ------------------------------------------------------------
    # youtu.be
    # ------------------------------------------------------------

    if hostname == "youtu.be":

        match = re.match(
            r"^/([A-Za-z0-9_-]{11})(?:/|$)",
            pathname
        )

        if match:
            return match.group(1)


    return None


# ================================================================
# TIMESTAMP FORMATTER
# ================================================================

def format_timestamp(start):
    """
    Convert transcript start time into MM:SS.

    Example:

        0       -> 00:00
        12.5    -> 00:12
        83.2    -> 01:23
        3725    -> 62:05

    The youtube-transcript-api normally returns start time
    in seconds. This function also defensively handles values
    that appear to be milliseconds.
    """

    try:
        seconds = float(start or 0)

    except (
        TypeError,
        ValueError
    ):
        seconds = 0.0


    # ------------------------------------------------------------
    # Defensive millisecond detection.
    #
    # Normal YouTube transcript timestamps are seconds.
    # If an unexpectedly large value is supplied, interpret it
    # as milliseconds.
    # ------------------------------------------------------------

    if seconds >= 100000:
        seconds = seconds / 1000.0


    seconds = max(
        0,
        int(seconds)
    )


    minutes = seconds // 60

    remaining_seconds = seconds % 60


    return (
        f"{minutes:02d}:"
        f"{remaining_seconds:02d}"
    )


# ================================================================
# TRANSCRIPT ITEM EXTRACTION
# ================================================================

def get_item_value(item, key, default=None):
    """
    Read a transcript item regardless of whether the library
    returns a dictionary-like object or an object with attributes.
    """

    if isinstance(item, dict):

        return item.get(
            key,
            default
        )


    return getattr(
        item,
        key,
        default
    )


# ================================================================
# NORMALIZE TRANSCRIPT
# ================================================================

def normalize_transcript(fetched_transcript):
    """
    Convert youtube-transcript-api output into the exact response
    format required by the website:

    [
        {
            "timestamp": "00:12",
            "text": "Hello world"
        }
    ]
    """

    # New youtube-transcript-api versions return FetchedTranscript
    # objects which expose .snippets.
    snippets = getattr(
        fetched_transcript,
        "snippets",
        None
    )


    # Defensive fallback for raw list output.
    if snippets is None:
        snippets = fetched_transcript


    result = []


    if not snippets:
        return result


    for item in snippets:

        start = get_item_value(
            item,
            "start",
            0
        )


        text = get_item_value(
            item,
            "text",
            ""
        )


        if text is None:
            continue


        text = str(text).strip()


        if not text:
            continue


        result.append(
            {
                "timestamp":
                    format_timestamp(start),

                "text":
                    text
            }
        )


    return result


# ================================================================
# FIND TRANSCRIPT
# ================================================================

def fetch_best_transcript(video_id):
    """
    Fetch the best available transcript.

    Priority:

        1. English
        2. Hindi

    For each language youtube-transcript-api prefers a manually
    created transcript over an automatically generated transcript.

    We intentionally check English first, then Hindi, because the
    requested API behavior is to try both languages.
    """

    api = YouTubeTranscriptApi()


    # ------------------------------------------------------------
    # First try English.
    # ------------------------------------------------------------

    try:

        transcript = api.fetch(
            video_id,
            languages=["en"]
        )

        return (
            transcript,
            "en"
        )


    except NoTranscriptFound:
        pass


    except (
        TranscriptsDisabled,
        VideoUnavailable,
        RequestBlocked,
        IpBlocked,
        CouldNotRetrieveTranscript
    ):
        # These errors can mean there is no usable English
        # transcript. We continue to Hindi where appropriate.
        pass


    except Exception:
        # Keep Hindi as a fallback for unexpected provider errors.
        pass


    # ------------------------------------------------------------
    # Then try Hindi.
    # ------------------------------------------------------------

    try:

        transcript = api.fetch(
            video_id,
            languages=["hi"]
        )

        return (
            transcript,
            "hi"
        )


    except Exception as exc:

        # Re-raise the final exception so the caller can convert
        # it into the clean public error response.
        raise exc


# ================================================================
# REQUEST HANDLER
# ================================================================

class handler(BaseHTTPRequestHandler):
    """
    Vercel Python Serverless Function handler.

    Vercel officially supports a handler class inheriting from
    http.server.BaseHTTPRequestHandler for Python Functions.
    """


    # ------------------------------------------------------------
    # Reduce default server logging noise.
    # ------------------------------------------------------------

    def log_message(
        self,
        format_string,
        *args
    ):
        return


    # ------------------------------------------------------------
    # OPTIONS
    # ------------------------------------------------------------

    def do_OPTIONS(self):
        """
        Handle CORS preflight requests.
        """

        self.send_response(204)

        add_cors_headers(self)

        self.end_headers()


    # ------------------------------------------------------------
    # GET
    # ------------------------------------------------------------

    def do_GET(self):
        """
        Main API endpoint.

        Expected:

            GET /api?url=YOUTUBE_URL
        """

        try:

            # ----------------------------------------------------
            # Parse URL
            # ----------------------------------------------------

            parsed_request = urlparse(
                self.path
            )


            # ----------------------------------------------------
            # Parse query parameters
            # ----------------------------------------------------

            query = parse_qs(
                parsed_request.query
            )


            url_values = query.get(
                "url",
                []
            )


            # ----------------------------------------------------
            # Validate URL parameter
            # ----------------------------------------------------

            if not url_values:

                send_json(
                    self,
                    {
                        "error":
                            "Please provide a YouTube URL."
                    },
                    400
                )

                return


            youtube_url = url_values[0]


            # ----------------------------------------------------
            # Extract video ID
            # ----------------------------------------------------

            video_id =
                extract_video_id(
                    youtube_url
                )


            if not video_id:

                send_json(
                    self,
                    {
                        "error":
                            INVALID_URL_MESSAGE
                    },
                    400
                )

                return


            # ----------------------------------------------------
            # Fetch transcript
            # ----------------------------------------------------

            fetched_transcript, language = (
                fetch_best_transcript(
                    video_id
                )
            )


            # ----------------------------------------------------
            # Normalize transcript
            # ----------------------------------------------------

            transcript = normalize_transcript(
                fetched_transcript
            )


            # ----------------------------------------------------
            # No usable transcript
            # ----------------------------------------------------

            if not transcript:

                send_json(
                    self,
                    {
                        "error":
                            ERROR_MESSAGE
                    },
                    404
                )

                return


            # ----------------------------------------------------
            # SUCCESS
            # ----------------------------------------------------

            send_json(
                self,
                {
                    "success": True,

                    "video_id":
                        video_id,

                    "language":
                        language,

                    "transcript":
                        transcript
                },
                200
            )


        # --------------------------------------------------------
        # Known transcript errors
        # --------------------------------------------------------

        except (
            TranscriptsDisabled,
            NoTranscriptFound,
            VideoUnavailable,
            CouldNotRetrieveTranscript,
            RequestBlocked,
            IpBlocked
        ):

            send_json(
                self,
                {
                    "error":
                        ERROR_MESSAGE
                },
                404
            )


        # --------------------------------------------------------
        # Network / YouTube / unexpected errors
        # --------------------------------------------------------

        except Exception as exc:

            # Do not expose internal exception details to users.
            #
            # This is intentionally generic because provider
            # exceptions can reveal implementation details.

            send_json(
                self,
                {
                    "error":
                        ERROR_MESSAGE
                },
                502
            )
