import ckan.plugins.toolkit as toolkit


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
