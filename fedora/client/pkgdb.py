# -*- coding: utf-8 -*-
#
# Copyright © 2008  Red Hat, Inc. All rights reserved.
#
# This copyrighted material is made available to anyone wishing to use, modify,
# copy, or redistribute it subject to the terms and conditions of the GNU
# General Public License v.2.  This program is distributed in the hope that it
# will be useful, but WITHOUT ANY WARRANTY expressed or implied, including the
# implied warranties of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.  You should have
# received a copy of the GNU General Public License along with this program;
# if not, write to the Free Software Foundation, Inc., 51 Franklin Street,
# Fifth Floor, Boston, MA 02110-1301, USA. Any Red Hat trademarks that are
# incorporated in the source code or documentation are not subject to the GNU
# General Public License and may only be used or replicated with the express
# permission of Red Hat, Inc.
#
# Author(s): Toshio Kuratomi <tkuratom@redhat.com>
# Author(s): Mike Watters <valholla@fedoraproject.org>
#
'''Module to provide a library interface to the package database.

.. moduleauthor:: Toshio Kuratomi <tkuratom@redhat.com>
.. moduleauthor:: Mike Watters <valholla@fedoraproject.org>

.. versionadded:: 0.3.6
   Merge from CLI pkgdb-client

.. data:: COLLECTIONMAP

    Maps short names to Collections.  For instance, FC => Fedora
'''

import simplejson

from fedora import __version__, _
from fedora.client import BaseClient, FedoraClientError, AppError

COLLECTIONMAP = {'F': 'Fedora',
    'FC': 'Fedora',
    'EL': 'Fedora EPEL',
    'EPEL': 'Fedora EPEL',
    'OLPC': 'Fedora OLPC',
    'RHL': 'Red Hat Linux'}

class PackageDBError(FedoraClientError):
    '''Errors generated by the PackageDB Client.'''
    pass

### FIXME: Port Exceptions on the server
# The PackageDB server returns errors errors as a dict with:
#   {'status': False, 'message': 'error message'}
# The new way of doing this is to set
#   {'exc': 'Exception name', tg_flash: 'error message'}
# So this needs to be ported on the server and we need to change error
# checking code to something like this:
# request = self.send_request([...])
# if 'exc' in request:
#   raise AppError(name=request['exc'], message=request['tg_flash'])
#
# Everywhere that currently sets AppError(name='PackageDBError',[...]) will
# need to be changed.

class PackageDB(BaseClient):
    '''Provide an easy to use interface to the PackageDB.'''
    def __init__(self, base_url='https://admin.fedoraproject.org/pkgdb/',
            *args, **kwargs):
        '''Create the PackageDB client.

        :kwarg base_url: Base of every URL used to contact the server.
            Defaults to the Fedora PackageDB instance.
        :kwarg useragent: useragent string to use.  If not given, default to
            "Fedora PackageDB Client/VERSION"
        :kwarg debug: If True, log debug information
        :type debug: bool
        :kwarg username: username for establishing authenticated connections
        :kwarg password: password to use with authenticated connections
        :kwarg session_id: user's session_id to connect to the server
        :type session_id: string
        :kwarg session_cookie: **Deprecated** use session_id instead.
            user's session_cookie to connect to the server
        :kwarg cache_session: if set to True, cache the user's session cookie
            on the filesystem between runs.
        :type kwarg: bool
        '''
        if 'useragent' not in kwargs:
            kwargs['useragent'] = 'Fedora PackageDB Client/%s' % __version__
        super(PackageDB, self).__init__(base_url, *args, **kwargs)

    def get_package_info(self, pkg, branch=None):
        '''Get information about the package.

        :arg pkg: Name of the package
        :kwarg branch: If given, restrict information returned to this branch
            Allowed branches are listed in :data:`COLLECTIONMAP`
        :raises AppError: If the server returns an exceptiom
        :returns: Package ownership information
        :rtype: fedora.client.DictContainer
        '''
        data = None
        if branch:
            collection, ver = self.canonical_branch_name(branch)
            data = {'collectionName': collection, 'collectionVersion': ver}
        pkg_info = self.send_request('/packages/name/%s' % pkg,
                req_params=data)

        if 'status' in pkg_info and not pkg_info['status']:
            raise AppError(name='PackageDBError', message=pkg_info['message'])
        return pkg_info

    def clone_branch(self, pkg, branch, master, email_log=True):
        '''Set a branch's permissions from a pre-existing branch.

        :arg pkg: Name of the package to branch
        :arg branch: Branch to clone to.  Allowed branch names are listed in
            :data:`COLLECTIONMAP`
        :arg master: Short branch name to clone from.  Allowed branch names
            are listed in :data:`COLLECTIONMAP`
        :kwarg email_log: If False, do not email a copy of the log.
        :raises AppError: If the server returns an exceptiom

        '''
        params = {'email_log': email_log}
        return self.send_request('/packages/dispatcher/clone_branch/'
                '%s/%s/%s' % (pkg, branch, master), auth=True,
                req_params=params)

    def mass_branch(self, branch):
        '''Branch all unblocked packages for a new release.

        Mass branching always works against the devel branch.

        :arg branch: Branch name to create branches for.  Names are listed in
            :data:`COLLECTIONMAP`
        :raises AppError: If the server returns an exceptiom.  The 'extras'
            attribute will contain a list of unbranched packages if some of the
            packages were branched
        '''
        return self.send_request('/collections/mass_branch/%s' % branch,
                auth=True)

    def add_edit_package(self, pkg, owner=None, description=None,
            branches=None, cc_list=None, comaintainers=None, groups=None):
        '''Add or edit a package to the database.

        :arg pkg: Name of the package to edit
        :kwarg owner: If set, make this person the owner of both branches
        :kwarg description: If set, make this the description of both branches
        :kwarg branches: List of branches to operate on
        :kwarg cc_list: If set, list or tuple of usernames to watch the
            package.
        :kwarg comaintainers: If set, list or tuple of usernames to comaintain
            the package.
        :kwarg groups: If set, list or tuple of group names that can commit to
            the package.
        :raises AppError: If the server returns an error

        This method takes information about a package and either edits the
        package to reflect the changes to information or adds the package to
        the database.

        Note: This method will be going away in favor of methods that do
        smaller chunks of work:

        1) A method to add a new package
        2) A method to add a new branch
        3) A method to edit an existing package
        4) A method to edit and existing branch
        '''
        # Check if the package exists
        try:
            self.get_package_info(pkg)
        except AppError:
            # Package doesn't exist yet.  See if we have the information to
            # create it
            if owner:
                if 'devel' not in branches:
                    # automatically add a devel branch to new packages
                    branches.append('devel')

                data = {'package': pkg, 'owner': owner, 'summary': description}
                # This call creates the package and an initial branch for
                # Fedora devel
                response = self.send_request('/packages/dispatcher/add_package',
                    auth=True, req_params=data)
                if 'status' in response and not response['status']:
                    raise AppError(name='PackageDBError', message=
                        _('PackageDB returned an error creating %(pkg)s:'
                        ' %(msg)s') % {'pkg': pkg, 'msg': response['message']})
                owner = None
                description = None
            else:
                raise PackageDBError, _('Package %(pkg)s does not exist and we'
                        ' do not have enough information to create it.') % \
                                {'pkg': pkg}

        # Change the branches, owners, or anything else that needs changing
        data = {}
        if owner:
            data['owner'] = owner
        if description:
            data['summary'] = description
        if cc_list:
            data['ccList'] = simplejson.dumps(cc_list)
        if comaintainers:
            data['comaintList'] = simplejson.dumps(comaintainers)

        # Parse the groups information
        if groups:
            data['groups'] = simplejson.dumps(groups)

        # Parse the Branch abbreviations into collections
        if branches:
            data['collections'] = []
            data['collections'] = branches

        # Request the changes
        response = self.send_request('/packages/dispatcher/edit_package/%s'
                % pkg, auth=True, req_params=data)
        if 'status' in response and not response['status']:
            raise AppError(name='PackageDBError', message=_('Unable to save'
                ' all information for %(pkg)s: %(msg)s') % {'pkg': pkg,
                    'msg': response['message']})

    def canonical_branch_name(self, branch):
        '''Change a branch abbreviation into a name and version.

        :arg branch: branch abbreviation
        :rtype: tuple
        :returns: tuple of branch name and branch version.

        Example:
        >>> name, version = canonical_branch_name('FC-6')
        >>> name
        Fedora
        >>> version
        6
        '''
        if branch == 'devel':
            collection = 'Fedora'
            version = 'devel'
        else:
            collection, version = branch.split('-')
            try:
                collection = COLLECTIONMAP[collection]
            except KeyError:
                raise PackageDBError(_('Collection abbreviation'
                        ' %(collection)s is unknown.  Use F, FC, EL, or OLPC')
                        % {'collection': collection})

        return collection, version

    def get_owners(self, package, collection=None, collection_ver=None):
        '''Retrieve the ownership information for a package.

        :arg package: Name of the package to retrieve package information about.
        :kwarg collection: Limit the returned information to this collection
            ('Fedora', 'Fedora EPEL', Fedora OLPC', etc)
        :kwarg collection_ver: If collection is specified, further limit to this
            version of the collection.
        :raises AppError: If the server returns an error
        :rtype: DictContainer
        :return: dict of ownership information for the package
        '''
        method = '/packages/name/%s' % package
        if collection:
            method = method + '/' + collection
            if collection_ver:
                method = method + '/' + collection_ver

        response = self.send_request(method)
        if 'status' in response and not response['status']:
            raise AppError(name='PackageDBError', message=response['message'])
        ###FIXME: Really should reformat the data so we show either a
        # dict keyed by collection + version or
        # list of collection, version, owner
        return response

    def remove_user(self, username, pkg_name, collectn_list=None):
        '''Remove user from a package

        :arg username: Name of user to remove from the package
        :arg pkg_name: Name of the package
        :kwarg collectn_list: list of collections like 'F-10','devel'.
            Default: None which means user removed from all collections
            associated with the package.
        :returns: status code from the request

        .. versionadded:: 0.3.12
        '''
        if collectn_list:
            params={'username': username, 'pkg_name': pkg_name, 
                'collectn_list': collectn_list}
        else:
            params={'username': username, 'pkg_name': pkg_name}
        return self.send_request('/packages/dispatcher/remove_user', auth=True,
                   req_params=params)
