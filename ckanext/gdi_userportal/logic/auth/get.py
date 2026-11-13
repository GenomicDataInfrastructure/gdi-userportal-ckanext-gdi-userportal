# SPDX-FileCopyrightText: 2024 Stichting Health-RI
#
# SPDX-License-Identifier: Apache-2.0

import ckan.plugins.toolkit as toolkit
from ckan import authz, model

from ckanext.gdi_userportal import profile_visibility


@toolkit.chained_auth_function
@toolkit.auth_allow_anonymous_access
def package_show(next_auth, context, data_dict=None):
    '''
    A dataset of a harvest source whose metadata profile is not enabled is not found, except for sysadmins
    (see profile_visibility). The harvester and the indexer skip authorisation (ignore_auth) and see everything.
    '''
    package = context.get('package')
    if package is not None and not authz.is_sysadmin(context.get('user')):
        enabled = profile_visibility.enabled_profiles(toolkit.config.get(profile_visibility.ENABLED_PROFILES_OPTION))
        if profile_visibility.is_hidden(model.Session, enabled, package.id):
            raise toolkit.ObjectNotFound(toolkit._('Dataset not found'))
    return next_auth(context, data_dict)


@toolkit.chained_auth_function
@toolkit.auth_allow_anonymous_access
def config_option_show(next_auth, context, data_dict=None):
    '''
    Change the original Auth function (ust for Sysadmins),
    To Allow for ignore_auth functionality (Originally set in ckanext-notifications)
    To allow the "ckanext.gdi_userportal.intro_text" Config Option to be publicly accessible
    '''
    if data_dict is None:
        data_dict = {}

    if context.get('ignore_auth', False) or data_dict.get('key') == 'ckanext.gdi_userportal.intro_text':
        return {'success': True}

    return next_auth(context, data_dict)


@toolkit.auth_allow_anonymous_access
def gdi_filter_help_texts_show(context, data_dict=None):
    return {"success": True}


@toolkit.auth_allow_anonymous_access
def gdi_dataset_help_texts_show(context, data_dict=None):
    return {"success": True}


@toolkit.auth_allow_anonymous_access
def gdi_metadata_profile_conformance(context, data_dict=None):
    # Reading the dataset is checked by the package_show call inside the action.
    return {"success": True}
