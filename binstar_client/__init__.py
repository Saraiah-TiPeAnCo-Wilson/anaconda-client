from __future__ import unicode_literals
import base64
import json
import os
import requests
import warnings

# For backwards compatibility
from .errors import *
from . import errors
from .requests_ext import stream_multipart

from .utils import compute_hash, jencode, pv
from .utils.http_codes import STATUS_CODES

from .mixins.organizations import OrgMixin
from .mixins.channels import ChannelsMixin
from .mixins.package import PackageMixin

import logging
import platform

log = logging.getLogger('binstar')

try:
    from ._version import __version__
except:
    __version__ = '0.8'

class Binstar(OrgMixin, ChannelsMixin, PackageMixin):
    '''
    An object that represents interfaces with the anaconda.org restful API.

    :param token: a token generated by Binstar.authenticate or None for
                  an anonymous user.
    '''

    def __init__(self, token=None, domain='https://api.anaconda.org', verify=True):

        self._session = requests.Session()
        self._session.headers['x-binstar-api-version'] = __version__
        self.session.verify = verify
        self.token = token

        if token:
            self._session.headers.update({'Authorization': 'token %s' % (token),
                                          'User-Agent': 'Binstar/%s (+https://anaconda.org)' % __version__})

        if domain.endswith('/'):
            domain = domain[:-1]
        self.domain = domain

    @property
    def session(self):
        return self._session

    def authenticate(self, username, password,
                     application, application_url=None,
                     for_user=None,
                     scopes=None,
                     created_with=None,
                     max_age=None,
                     strength='strong',
                     fail_if_already_exists=False,
                     hostname=platform.node()):
        '''
        Use basic authentication to create an authentication token using the interface below.
        With this technique, a username and password need not be stored permanently, and the user can
        revoke access at any time.

        :param username: The users name
        :param password: The users password
        :param application: The application that is requesting access
        :param application_url: The application's home page
        :param scopes: Scopes let you specify exactly what type of access you need. Scopes limit access for the tokens.
        '''

        url = '%s/authentications' % (self.domain)
        payload = {"scopes": scopes, "note": application, "note_url": application_url,
                   'hostname': hostname,
                   'user': for_user,
                   'max-age': max_age,
                   'created_with': None,
                   'strength': strength,
                   'fail-if-exists': fail_if_already_exists}

        data, headers = jencode(payload)
        res = self.session.post(url, auth=(username, password), data=data, headers=headers)
        self._check_response(res)
        res = res.json()
        token = res['token']
        self.session.headers.update({'Authorization': 'token %s' % (token)})
        return token

    def list_scopes(self):
        url = '%s/scopes' % (self.domain)
        res = requests.get(url)
        self._check_response(res)
        return res.json()

    def authentication(self):
        '''
        Retrieve information on the current authentication token
        '''
        url = '%s/authentication' % (self.domain)
        res = self.session.get(url)
        self._check_response(res)
        return res.json()

    def authentications(self):
        '''
        Get a list of the current authentication tokens
        '''

        url = '%s/authentications' % (self.domain)
        res = self.session.get(url)
        self._check_response(res)
        return res.json()

    def remove_authentication(self, auth_name=None):
        """
        Remove the current authentication or the one given by `auth_name`
        """
        if auth_name:
            url = '%s/authentications/name/%s' % (self.domain, auth_name)
        else:
            url = '%s/authentications' % (self.domain,)

        res = self.session.delete(url)
        self._check_response(res, [201])

    def _check_response(self, res, allowed=[200]):
        api_version = res.headers.get('x-binstar-api-version', '0.2.1')
        if pv(api_version) > pv(__version__):
            msg = ('The api server is running the binstar-api version %s. you are using %s\n' % (api_version, __version__)
                   + 'Please update your client with pip install -U binstar or conda update binstar')
            warnings.warn(msg, stacklevel=4)


        if not res.status_code in allowed:
            short, long = STATUS_CODES.get(res.status_code, ('?', 'Undefined error'))
            msg = '%s: %s ([%s] %s -> %s)' % (short, long, res.request.method, res.request.url, res.status_code)
            try:
                data = res.json()
            except:
                pass
            else:
                msg = data.get('error', msg)

            ErrCls = errors.BinstarError
            if res.status_code == 401:
                ErrCls = errors.Unauthorized
            elif res.status_code == 404:
                ErrCls = errors.NotFound
            elif res.status_code == 409:
                ErrCls = errors.Conflict
            elif res.status_code >= 500:
                ErrCls = errors.ServerError

            raise ErrCls(msg, res.status_code)

    def user(self, login=None):
        '''
        Get user infomration.

        :param login: (optional) the login name of the user or None. If login is None
                      this method will return the information of the authenticated user.
        '''
        if login:
            url = '%s/user/%s' % (self.domain, login)
        else:
            url = '%s/user' % (self.domain)

        res = self.session.get(url, verify=self.session.verify)
        self._check_response(res)

        return res.json()

    def user_packages(self, login=None):
        '''
        Returns a list of packages for a given user

        :param login: (optional) the login name of the user or None. If login is None
                      this method will return the packages for the authenticated user.

        '''
        if login:
            url = '%s/packages/%s' % (self.domain, login)
        else:
            url = '%s/packages' % (self.domain)

        res = self.session.get(url)
        self._check_response(res)

        return res.json()

    def package(self, login, package_name):
        '''
        Get infomration about a specific package

        :param login: the login of the package owner
        :param package_name: the name of the package
        '''
        url = '%s/package/%s/%s' % (self.domain, login, package_name)
        res = self.session.get(url)
        self._check_response(res)
        return res.json()

    def package_add_collaborator(self, owner, package_name, collaborator):
        url = '%s/packages/%s/%s/collaborators/%s' % (self.domain, owner, package_name, collaborator)
        res = self.session.put(url)
        self._check_response(res, [201])
        return

    def package_remove_collaborator(self, owner, package_name, collaborator):
        url = '%s/packages/%s/%s/collaborators/%s' % (self.domain, owner, package_name, collaborator)
        res = self.session.delete(url)
        self._check_response(res, [201])
        return

    def package_collaborators(self, owner, package_name):

        url = '%s/packages/%s/%s/collaborators' % (self.domain, owner, package_name)
        res = self.session.get(url)
        self._check_response(res, [200])
        return res.json()

    def all_packages(self, modified_after=None):
        '''
        '''
        url = '%s/package_listing' % (self.domain)
        data = {'modified_after':modified_after or ''}
        res = self.session.get(url, data=data)
        self._check_response(res)
        return res.json()


    def add_package(self, login, package_name,
                    summary=None,
                    license=None,
                    public=True,
                    license_url=None,
                    attrs=None):
        '''
        Add a new package to a users account

        :param login: the login of the package owner
        :param package_name: the name of the package to be created
        :param package_type: A type identifyer for the package (eg. 'pypi' or 'conda', etc.)
        :param summary: A short summary about the package
        :param license: the name of the package license
        :param license_url: the url of the package license
        :param public: if true then the package will be hosted publicly
        :param attrs: A dictionary of extra attributes for this package
        '''
        url = '%s/package/%s/%s' % (self.domain, login, package_name)

        attrs = attrs or {}
        attrs['summary'] = summary
        attrs['license'] = {'name':license, 'url':license_url}

        payload = dict(public=bool(public),
                       publish=False,
                       public_attrs=dict(attrs or {})
                       )

        data, headers = jencode(payload)
        res = self.session.post(url, data=data, headers=headers)
        self._check_response(res)
        return res.json()

    def remove_package(self, username, package_name):

        url = '%s/package/%s/%s' % (self.domain, username, package_name)

        res = self.session.delete(url)
        self._check_response(res, [201])
        return

    def release(self, login, package_name, version):
        '''
        Get information about a specific release

        :param login: the login of the package owner
        :param package_name: the name of the package
        :param version: the name of the package
        '''
        url = '%s/release/%s/%s/%s' % (self.domain, login, package_name, version)
        res = self.session.get(url)
        self._check_response(res)
        return res.json()

    def remove_release(self, username, package_name, version):
        '''
        remove a release and all files under it

        :param username: the login of the package owner
        :param package_name: the name of the package
        :param version: the name of the package
        '''
        url = '%s/release/%s/%s/%s' % (self.domain, username, package_name, version)
        res = self.session.delete(url)
        self._check_response(res, [201])
        return

    def add_release(self, login, package_name, version, requirements, announce, description):
        '''
        Add a new release to a package.

        :param login: the login of the package owner
        :param package_name: the name of the package
        :param version: the version string of the release
        :param requirements: A dict of requirements TODO: describe
        :param announce: An announcement that will be posted to all package watchers
        :param description: A long description about the package
        '''

        url = '%s/release/%s/%s/%s' % (self.domain, login, package_name, version)

        payload = {'requirements':requirements, 'announce':announce, 'description':description}
        data, headers = jencode(payload)
        res = self.session.post(url, data=data, headers=headers)
        self._check_response(res)
        return res.json()

    def distribution(self, login, package_name, release, basename=None):

        url = '%s/dist/%s/%s/%s/%s' % (self.domain, login, package_name, release, basename)

        res = self.session.get(url)
        self._check_response(res)
        return res.json()

    def remove_dist(self, login, package_name, release, basename=None, _id=None):

        if basename:
            url = '%s/dist/%s/%s/%s/%s' % (self.domain, login, package_name, release, basename)
        elif _id:
            url = '%s/dist/%s/%s/%s/-/%s' % (self.domain, login, package_name, release, _id)
        else:
            raise TypeError("method remove_dist expects either 'basename' or '_id' arguments")

        res = self.session.delete(url)
        self._check_response(res)
        return res.json()


    def download(self, login, package_name, release, basename, md5=None):
        '''
        Dowload a package distribution

        :param login: the login of the package owner
        :param package_name: the name of the package
        :param version: the version string of the release
        :param basename: the basename of the distribution to download
        :param md5: (optional) an md5 hash of the download if given and the package has not changed
                    None will be returned

        :returns: a file like object or None
        '''

        url = '%s/download/%s/%s/%s/%s' % (self.domain, login, package_name, release, basename)
        if md5:
            headers = {'ETag':md5, }
        else:
            headers = {}

        res = self.session.get(url, headers=headers, allow_redirects=False)
        self._check_response(res, allowed=[302, 304])

        if res.status_code == 304:
            return None
        elif res.status_code == 302:
            res2 = requests.get(res.headers['location'], stream=True)
            return res2


    def upload(self, login, package_name, release, basename, fd, distribution_type,
               description='', md5=None, size=None, dependencies=None, attrs=None, channels=('main',), callback=None):
        '''
        Upload a new distribution to a package release.

        :param login: the login of the package owner
        :param package_name: the name of the package
        :param version: the version string of the release
        :param basename: the basename of the distribution to download
        :param fd: a file like object to upload
        :param description: (optional) a short description about the file
        :param attrs: any extra attributes about the file (eg. build=1, pyversion='2.7', os='osx')

        '''
        url = '%s/stage/%s/%s/%s/%s' % (self.domain, login, package_name, release, basename)
        if attrs is None:
            attrs = {}
        if not isinstance(attrs, dict):
            raise TypeError('argument attrs must be a dictionary')

        payload = dict(distribution_type=distribution_type, description=description, attrs=attrs,
                       dependencies=dependencies, channels=channels)

        data, headers = jencode(payload)
        res = self.session.post(url, data=data, headers=headers)
        self._check_response(res)
        obj = res.json()

        s3url = obj['post_url']
        s3data = obj['form_data']

        if md5 is None:
            _hexmd5, b64md5, size = compute_hash(fd, size=size)
        elif size is None:
            spos = fd.tell()
            fd.seek(0, os.SEEK_END)
            size = fd.tell() - spos
            fd.seek(spos)

        s3data['Content-Length'] = size
        s3data['Content-MD5'] = b64md5

        data_stream, headers = stream_multipart(s3data, files={'file':(basename, fd)},
                                                callback=callback)

        s3res = requests.post(s3url, data=data_stream, verify=self.session.verify, timeout=10 * 60 * 60, headers=headers)

        if s3res.status_code != 201:
            log.info(s3res.text)
            log.info('')
            log.info('')
            raise errors.BinstarError('Error uploading package', s3res.status_code)

        url = '%s/commit/%s/%s/%s/%s' % (self.domain, login, package_name, release, basename)
        payload = dict(dist_id=obj['dist_id'])
        data, headers = jencode(payload)
        res = self.session.post(url, data=data, headers=headers)
        self._check_response(res)

        return res.json()

    def search(self, query, package_type=None):
        url = '%s/search' % self.domain
        res = self.session.get(url, params={'name':query, 'type':package_type})
        self._check_response(res)
        return res.json()

