from ipynbsrv.contract.backends import UserGroupBackend
import ldap
import sys


class Ldap(UserGroupBackend):
    '''
    Implemented by looking at the following sources:

    https://www.packtpub.com/books/content/python-ldap-applications-part-1-installing-and-configuring-python-ldap-library-and-bin
    https://www.packtpub.com/books/content/python-ldap-applications-part-3-more-ldap-operations-and-ldap-url-library

    tested:
        create_user
        create_group
        delete_user
        delete_group
        rename_user
        rename_group

    '''

    '''
    Key to be used in returns as unique identifier for the group.
    '''
    FIELD_GROUP_PK = 'cn'

    '''
    Key to be used in returns as unique identifier for the user.
    '''
    FIELD_USER_PK = 'cn'

    def __init__(self, ldap_server, admin_dn, admin_pw,
                 user_base_dn='ou=users,dc=ipynbsrv,dc=ldap',
                 group_base_dn='ou=groups,dc=ipynbsrv,dc=ldap'
                 ):
        '''
        Create a Ldap Connector

        Args:
            ldap_server:    Hostname or IP of the LDAP server           
            admin_dn:       dn of the LDAP admin user
            admin_pw:       admin password
            user_base_dn:   Base DN for users (default: ou=users,dc=ipynbsrv,dc=ldap)
            group_base_dn:  Base DN for groups (default: ou=groups,dc=ipynbsrv,dc=ldap)
        '''
        if not "ldap://" in ldap_server:
            ldap_server = "ldap://" + ldap_server

        self.ldap_server = ldap_server
        self.server = ldap_server
        self.admin_dn = admin_dn
        self.admin_pw = admin_pw
        self.user_base_dn = user_base_dn
        self.group_base_dn = group_base_dn

    ''' Helper Functions ------------------------------------ '''

    def open_connection(self):
        try:
            self.conn = ldap.initialize(self.server)
            self.conn.bind_s(self.admin_dn, self.admin_pw)
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

    def get_dn_by_username(self, username):
        return "cn={0},{1}".format(username, self.user_base_dn)

    def get_dn_by_groupname(self, groupname):
        return "cn={0},{1}".format(groupname, self.group_base_dn)


    ''' User Functions ------------------------------------ '''

    def get_user(self, pk, **kwargs):
        try:
            self.open_connection()

            dn = self.get_dn_by_username(pk)
            return self.conn.read_s(dn)
        finally:
            self.close_connection()

    def get_users(self, **kwargs):
        try:
            self.open_connection()

            return self.conn.search_s(self.user_base_dn, ldap.BASE_SUBTREE)
        finally:
            self.close_connection()

    def get_users_in_group(self, group, **kwargs):
        # TODO: what defines user - group relation?
        raise NotImplmentedError

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
        try:
            self.open_connection()

            dn = self.get_dn_by_username(user)
            mod_attrs = [(ldap.MOD_REPLACE, 'userpassword', password)]
            self.conn.modify_s(dn, mod_attrs)
        finally:
            self.close_connection()

    def delete_user(self, user, **kwargs):
        try:
            self.open_connection()

            dn = self.get_dn_by_username(user)
            self.conn.delete(dn)
        finally:
            self.close_connection()

    def add_user_to_group(self, user, group, **kwargs):
        # TODO: check gid
        try:
            self.open_connection

            dn = self.get_dn_by_username(user)
            mod_attrs = [(ldap.MOD_ADD, 'gidNumber', [group])]
            self.conn.modify_s(dn, mod_attrs)
        finally:
            self.close_connection()

    def remove_user_from_group(self, user, group, **kwargs):
        # TODO: check gid
        try:
            self.open_connection

            dn = self.get_dn_by_username(user)
            mod_attrs = [(ldap.MOD_DELETE, 'gidNumber', [group])]
            self.conn.modify_s(dn, mod_attrs)
        finally:
            self.close_connection()

        '''
        Returns a list of field names the backend expects the input objects
        to the create_user method to have at least.

        The list should contain tuples in the form: (name, type)
        '''
        def get_required_user_creation_fields(self):
            return [("username", str), ("password", str)]

    ''' Group Functions ------------------------------------ '''

    def create_group(self, specification, **kwargs):
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
        try:
            self.open_connection()

            dn = self.get_dn_by_groupname(groupname)

            # copy object to new dn and delete old one
            self.conn.modrdn_s(dn, "cn={0}".format(new_name), delold=1)

        finally:
            self.close_connection()

    def delete_group(self, group):
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
