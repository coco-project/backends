from ipynbsrv.contract.backends import UserBackend, GroupBackend
from ipynbsrv.contract.errors import ConnectionError, GroupBackendError, GroupNotFoundError, ReadOnlyError, UserBackendError, UserNotFoundError
from django.contrib.auth.hashers import make_password
import ldap
import sys


class LdapBackend(GroupBackend, UserBackend):
    '''
    Group- and UserBackend implementation communicating with an LDAP server.

    Implemented by looking at the following sources:

    https://www.packtpub.com/books/content/python-ldap-applications-part-1-installing-and-configuring-python-ldap-library-and-bin
    https://www.packtpub.com/books/content/python-ldap-applications-part-3-more-ldap-operations-and-ldap-url-library

    '''

    def __init__(self, server, user, pw,
                 user_base_dn='ou=users,dc=ipynbsrv,dc=ldap',
                 group_base_dn='ou=groups,dc=ipynbsrv,dc=ldap',
                 readonly=True,
                 user_pk='cn',
                 group_pk='cn'
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
        # Key to be used in returns as unique identifier for the user.
        self.user_pk = user_pk
        # # Key to be used in returns as unique identifier for the group.
        self.group_pk = group_pk

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

    def connect(self, credentials, **kwargs):
        try:
            self.conn = ldap.initialize(self.server)
            self.conn.bind_s(credentials['username'], credentials['password'])
        except:
            print("connection failed, try again with username including user dn")
            try:
                self.conn = ldap.initialize(self.server)
                self.conn.bind_s(get_dn_by_username(credentials['username']), credentials['password'])
            except ldap.INVALID_CREDENTIALS:
                print("connection failed again with username including user dn")
                print("Your username or password is incorrect.")
                sys.exit()
            except ldap.LDAPError as e:
                if type(e.message) == dict and 'desc' in e.message:
                    print(e.message['desc'])
                else:
                    print(e)
                sys.exit()
            except Exception as e:
                print("unknown error")
                print(e)
                raise(ConnectionError)

    def disconnect(self, **kwargs):
        self.close_connection()

    def validate_login(self, credentials, **kwargs):
        try:
            self.connect(credentials)
            self.disconnect()
            return True
        except:
            return False

    def get_group(self, pk, **kwargs):
        try:
            self.open_connection()

            # set the scope for the search
            base = self.group_base_dn
            # set the search scope, subtree = search the base dn and all its sub-units
            scope = ldap.SCOPE_SUBTREE
            # set the search filter to be applied on the objects in the ldap directory
            s_filter = '{0}={1}'.format(self.group_pk, pk)
            print "s_filter: {0}".format(s_filter)
            print "conn.search_s('{0}', {1}, filterstr='{2}'')".format(base, scope, s_filter)

            try:
                u = self.conn.search_s(base, scope, filterstr=s_filter)
                # check if single user has been found
                if len(u) < 1:
                    raise GroupNotFoundError(pk)
                elif len(u) > 1:
                    raise GroupNotFoundError('Result not unique, {0} groups found. {1}'.format(len(u), pk))
                else:
                    # get the user dn
                    group_dn = u[0][0]
                    print group_dn
                    group_attrs = u[0][1]
                    group_attrs['pk'] = pk
                    group_attrs['dn'] = group_dn

                    return group_attrs
            except ldap.NO_SUCH_OBJECT:
                raise GroupNotFoundError(pk)

        finally:
            self.close_connection()

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

        groupname, gidNumber, memberUid = specification["groupname"], specification["gidNumber"], specification["memberUid"]

        if type(groupname) is not str:
            raise ValueError("Groupname must be a string")

        try:
            self.open_connection()

            dn = self.get_dn_by_groupname(groupname)

            add_record = [
                ('objectclass', ['posixGroup', 'top']),
                ('gidNumber', [gidNumber]),
                ('cn', [groupname]),
                ('memberUid', [memberUid])
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
        return [("groupname", str), ("gidNumber", str), ("memberUid", str)]

    def get_user(self, pk, **kwargs):
        try:
            self.open_connection()

            # set the scope for the search
            base = self.user_base_dn
            # set the search scope, subtree = search the base dn and all its sub-units
            scope = ldap.SCOPE_SUBTREE
            # set the search filter to be applied on the objects in the ldap directory
            s_filter = '{0}={1}'.format(self.user_pk, pk)
            print "s_filter: {0}".format(s_filter)
            print "conn.search_s('{0}', {1}, filterstr='{2}'')".format(base, scope, s_filter)

            try:
                u = self.conn.search_s(base, scope, filterstr=s_filter)
                # check if single user has been found
                if len(u) < 1:
                    raise UserNotFoundError(pk)
                elif len(u) > 1:
                    raise UserNotFoundError('Result not unique, {0} users found. {1}'.format(len(u), pk))
                else:
                    # get the user dn
                    user_dn = u[0][0]
                    print user_dn
                    user_attrs = u[0][1]
                    user_attrs['pk'] = pk
                    user_attrs['dn'] = user_dn

                    return user_attrs
            except ldap.NO_SUCH_OBJECT:
                raise UserNotFoundError(pk)

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

        # encrypt the password, using django internal tools
        username, password, uidNumber = specification["username"], str(make_password(specification["password"])), specification["uidNumber"]

        try:
            self.open_connection()

            dn = self.get_dn_by_username(username)

            # create user
            add_record = [
                ('objectclass', ['person', 'organizationalperson', 'inetorgperson', 'posixAccount', 'top']),
                ('uid', [username]),
                ('uidNumber', [uidNumber]),
                ('gidNumber', [uidNumber]),
                ('cn', [username]),
                ('sn', [username]),
                ('userpassword', [password]),
                ('homedirectory', ['/home/{}'.format(username)])
            ]
            self.conn.add_s(dn, add_record)

        finally:
            print("user created")
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
        return [("username", str), ("password", str), ("uidNumber", str), ("homedirectory", str)]
