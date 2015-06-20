from ipynbsrv.contract.backends import UserBackend, GroupBackend
from ipynbsrv.contract.backends import UserGroupBackendError, GroupNotFoundError, UserNotFoundError
import ldap
import sys


class ReadOnlyError(UserGroupBackendError):
    '''
    Backend error type for users/groups backends.
    '''
    pass


class LdapBackend(object):
    def __init__(self, server, user, pw,
                 user_base_dn='ou=users,dc=ipynbsrv,dc=ldap',
                 group_base_dn='ou=groups,dc=ipynbsrv,dc=ldap',
                 readonly=True
                 ):
        '''
        Create a Ldap Connector

        Args:
            server:    Hostname or IP of the LDAP server           
            user:       dn of the LDAP admin user
            pw:       admin password
            user_base_dn:   Base DN for users (default: ou=users,dc=ipynbsrv,dc=ldap)
            group_base_dn:  Base DN for groups (default: ou=groups,dc=ipynbsrv,dc=ldap)
        '''
        if "ldap://" not in server:
            server = "ldap://" + server

        self.server = server
        self.user = user
        self.pw = pw
        self.user_base_dn = user_base_dn
        self.group_base_dn = group_base_dn
        self.readonly = readonly

    def get_dn_by_username(self, username):
        return "cn={0},{1}".format(username, self.user_base_dn)

    def get_dn_by_groupname(self, groupname):
        return "cn={0},{1}".format(groupname, self.group_base_dn)

    ''' Helper Functions ------------------------------------ '''

    # TODO: improve Exception handling
    def open_connection(self):
        try:
            self.conn = ldap.initialize(self.server)
            self.conn.bind_s(self.user, self.pw)
        except ldap.INVALID_CREDENTIALS:
            print("Your username or password is incorrect.")
            sys.exit()
        except ldap.LDAPError as e:
            if type(e.message) == dict and 'desc' in e.message:
                print(e.message['desc'])
            else:
                print(e)
            sys.exit()

    def close_connection(self):
        try:
            self.conn.unbind()
        except Exception as e:
            print("Problem closing connection")
            if type(e.message) == dict and 'desc' in e.message:
                print(e.message['desc'])
            else:
                print(e)
            sys.exit()


class LdapGroupBackend(GroupBackend, LdapBackend):
    '''
    Key to be used in returns as unique identifier for the group.
    '''
    FIELD_GROUP_PK = 'cn'

    def get_users_by_group(self, group, **kwargs):
        try:
            self.open_connection()

            dn = self.get_dn_by_groupname(group)

            g = self.conn.read_s(dn)

            if 'memberUid' not in g:
                return []
            else:
                users = []
                for user in g['memberUid']:
                    users += [{'pk': user}]
                return users
        finally:
            self.close_connection()

    def add_user_to_group(self, user, group, **kwargs):
        if self.readonly:
            raise ReadOnlyError
        # TODO: check gid
        try:
            self.open_connection

            dn = self.get_dn_by_groupname(group)
            mod_attrs = [(ldap.MOD_ADD, 'memberUid', [user])]
            self.conn.modify_s(dn, mod_attrs)
        finally:
            self.close_connection()

    def remove_user_from_group(self, user, group, **kwargs):
        if self.readonly:
            raise ReadOnlyError
        # TODO: check gid
        try:
            self.open_connection

            dn = self.get_dn_by_groupname(group)
            mod_attrs = [(ldap.MOD_DELETE, 'memberUid', [user])]
            self.conn.modify_s(dn, mod_attrs)
        finally:
            self.close_connection()

    def create_group(self, specification, **kwargs):
        if self.readonly:
            raise ReadOnlyError
        if "groupname" not in specification:
            raise ValueError("Groupname needs to be provided")

        groupname = specification["groupname"]

        if type(groupname) is not str:
            raise ValueError("Groupname must be a string")

        try:
            self.open_connection()

            dn = self.get_dn_by_groupname(groupname)

            add_record = [
                ('objectclass', ['posixGroup', 'top']),
                ('gidNumber', ['2500']),  # Where does this come from?
                ('cn', [groupname]),
                ('memberUid', '')  # TODO: What goes here?
            ]
            self.conn.add_s(dn, add_record)
        finally:
            self.close_connection()

    def rename_group(self, groupname, new_name):
        if self.readonly:
            raise ReadOnlyError
        try:
            self.open_connection()

            dn = self.get_dn_by_groupname(groupname)

            # copy object to new dn and delete old one
            self.conn.modrdn_s(dn, "cn={0}".format(new_name), delold=1)

        finally:
            self.close_connection()

    def delete_group(self, group):
        if self.readonly:
            raise ReadOnlyError
        # TODO: what to do with users in that group?
        try:
            self.open_connection()

            dn = self.get_dn_by_groupname(group)
            self.conn.delete(dn)
        finally:
            self.close_connection()

    '''
    Returns a list of field names the backend expects the input objects
    to the create_group method to have at least.

    The list should contain tuples in the form: (name, type)
    '''
    def get_required_group_creation_fields(self):
        return [("groupname", str)]


class LdapUserBackend(UserBackend, LdapBackend):
    '''
    Implemented by looking at the following sources:

    https://www.packtpub.com/books/content/python-ldap-applications-part-1-installing-and-configuring-python-ldap-library-and-bin
    https://www.packtpub.com/books/content/python-ldap-applications-part-3-more-ldap-operations-and-ldap-url-library

    '''

    '''
    Key to be used in returns as unique identifier for the user.
    '''
    FIELD_USER_PK = 'cn'

    ''' User Functions ------------------------------------ '''

    def get_user(self, pk, **kwargs):
        try:
            self.open_connection()

            dn = self.get_dn_by_username(pk)
            try:
                u = self.conn.read_s(dn)
                u['pk'] = pk
                return u
            except ldap.NO_SUCH_OBJECT:
                raise UserNotFoundError()

        finally:
            self.close_connection()

    def get_users(self, **kwargs):
        try:
            self.open_connection()

            # Get list of users and remove dn, to only have dicts in the list
            # lda.SCOPE_ONELEVEL == 1, search only childs of dn
            users = map(lambda x: x[1], self.conn.search_s(self.user_base_dn, ldap.SCOPE_ONELEVEL))

            # Add pk to dict
            for u in users:
                u['pk'] = u['cn'][0]
            return users

        finally:
            self.close_connection()

    def create_user(self, specification, **kwargs):
        '''
        Creates LDAP user on the server

        Args:

            username:   name of the user to create
            password:   password for the new user

        Returns:

        Raises:

        Todo:
            Homedir in parameters?
        '''

        if self.readonly:
            raise ReadOnlyError

        for field in self.get_required_user_creation_fields():
            if field[0] not in specification:
                raise ValueError("{0} missing".format(field[0]))
            if field[1] is not field[1]:
                raise ValueError("{0} must be of type {1}".format(field[0], field[1]))

        username, password = specification["username"], specification["password"]

        try:
            self.open_connection()

            dn = self.get_dn_by_username(username)

            add_record = [
                ('objectclass', ['person', 'organizationalperson', 'inetorgperson', 'posixAccount', 'top']),
                ('uid', [username]),
                ('uidNumber', ['2500']),
                ('gidNumber', ['2500']),
                ('cn', [username]),
                ('sn', [username]),
                ('userpassword', [password]),
                ('homedirectory', ['/home/test'])
            ]
            self.conn.add_s(dn, add_record)
        finally:
            self.close_connection()

    def rename_user(self, user, new_name, **kwargs):
        if self.readonly:
            raise ReadOnlyError
        try:
            self.open_connection()

            dn = self.get_dn_by_username(user)

            # First: change name fields
            mod_attrs = [(ldap.MOD_REPLACE, 'uid', new_name),
                         (ldap.MOD_REPLACE, 'sn', new_name)
                         ]
            self.conn.modify_s(dn, mod_attrs)

            # Then: copy object to new dn and delete old one
            self.conn.modrdn_s(dn, "cn={0}".format(new_name), delold=1)

        finally:
            self.close_connection()

    def set_user_password(self, user, password, **kwargs):
        if self.readonly:
            raise ReadOnlyError
        try:
            self.open_connection()

            dn = self.get_dn_by_username(user)
            mod_attrs = [(ldap.MOD_REPLACE, 'userpassword', password)]
            self.conn.modify_s(dn, mod_attrs)
        finally:
            self.close_connection()

    def delete_user(self, user, **kwargs):
        if self.readonly:
            raise ReadOnlyError
        try:
            self.open_connection()

            dn = self.get_dn_by_username(user)
            self.conn.delete(dn)
        finally:
            self.close_connection()

    '''
    Returns a list of field names the backend expects the input objects
    to the create_user method to have at least.

    The list should contain tuples in the form: (name, type)
    '''
    def get_required_user_creation_fields(self):
        return [("username", str), ("password", str)]
