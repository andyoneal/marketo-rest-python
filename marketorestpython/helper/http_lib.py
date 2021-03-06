import mimetypes
import time

import backoff
import requests

from marketorestpython.helper.exceptions import MarketoException

retryable_error_codes = {
    '502': 'Bad Gateway',
    '604': 'Request timed out',
    '606': 'Max rate limit exceeded',
    '608': 'API Temporarily Unavailable',
    '615': 'Concurrent access limit reached',
    '713': 'Transient Error',
    '1014': 'Failed to create Object',
    '1016': 'Too many imports',
    '1019': 'Import in progress',
    '1022': 'Object in use',
    '1029': 'Too many jobs in queue'
}


def fatal_marketo_error_code(e):
    # Given a MarketoException, decide whether it is fatal or retryable.
    return e.code not in retryable_error_codes


class HttpLib:
    num_calls_per_second = 5  # five calls per second max (at 100/20 rate limit)

    def __init__(self, max_retry_time_conf):
        global max_retry_time
        max_retry_time = max_retry_time_conf

    def lookup_max_time():
        # this function is needed to dynamically set the max_time for backoff; should not have 'self'
        global max_retry_time
        return max_retry_time

    def _rate_limited(maxPerSecond):
        minInterval = 1.0 / float(maxPerSecond)
        def decorate(func):
            lastTimeCalled = [0.0]
            def rateLimitedFunction(*args,**kargs):
                elapsed = time.clock() - lastTimeCalled[0]
                leftToWait = minInterval - elapsed
                if leftToWait>0:
                    time.sleep(leftToWait)
                ret = func(*args,**kargs)
                lastTimeCalled[0] = time.clock()
                return ret
            return rateLimitedFunction
        return decorate

    @backoff.on_exception(backoff.expo, MarketoException,
                          max_time=lookup_max_time,
                          giveup=fatal_marketo_error_code)
    @_rate_limited(num_calls_per_second)
    def get(self, endpoint, args=None, mode=None):
        headers = {'Accept-Encoding': 'gzip'}
        r = requests.get(endpoint, params=args, headers=headers)
        if mode is 'nojson':
            return r
        else:
            r_json = r.json()
            if mode is 'accesstoken' or r_json.get('success'):
                return r_json
            else:
                raise MarketoException(r_json['errors'][0])

    @backoff.on_exception(backoff.expo, MarketoException,
                          max_time=lookup_max_time,
                          giveup=fatal_marketo_error_code)
    @_rate_limited(num_calls_per_second)
    def post(self, endpoint, args, data=None, files=None, filename=None,
             mode=None):
        if mode is 'nojsondumps':
            r = requests.post(endpoint, params=args, data=data)
        elif files is None:
            headers = {'Content-type': 'application/json'}
            r = requests.post(endpoint, params=args, json=data, headers=headers)
        elif files is not None:
            mimetype = mimetypes.guess_type(files)[0]
            file = {filename: (files, open(files, 'rb'), mimetype)}
            r = requests.post(endpoint, params=args, json=data, files=file)
        r_json = r.json()
        if r_json.get('success'):
            return r_json
        else:
            raise MarketoException(r_json['errors'][0])

    @backoff.on_exception(backoff.expo, MarketoException,
        max_time=lookup_max_time, giveup=fatal_marketo_error_code)
    @_rate_limited(num_calls_per_second)
    def delete(self, endpoint, args, data):
        headers = {'Content-type': 'application/json'}
        r = requests.delete(endpoint, params=args, json=data, headers=headers)
        r_json = r.json()
        if r_json.get('success'):
            return r.json()
        else:
            raise MarketoException(r_json['errors'][0])
