from ipynbsrv.contract.backends import *
import ldap


class Ldap(UserGroupBackend):
    '''
    Implemented by looking at the following sources:

    https://www.packtpub.com/books/content/python-ldap-applications-part-1-installing-and-configuring-python-ldap-library-and-bin
    https://www.packtpub.com/books/content/python-ldap-applications-part-3-more-ldap-operations-and-ldap-url-library

    '''

    def __init__(self, ldap_server, users_cn, user_base_dn, user_pw):
        self.server = ldap_server
        self.admin_dn = user_dn
        self.admin_pw = user_pw
        self.user_base_dn = user_base_dn
        self.group_base_dn = group_base_dn
        self.conn = ldap.initialize(self.server)

    def open_connection(self):
        try:
            #l.start_tls_s()
            self.conn.bind_s(self.admin_dn, self.admin_pw)
        except ldap.INVALID_CREDENTIALS:
            print("Your username or password is incorrect.")
            sys.exit()
        except ldap.LDAPError e:
            if type(e.message) == dict and e.message.has_key('desc'):
                print e.message['desc']
            else:
                print e
            sys.exit()

    def close_connection(self):
        try:
            self.conn.unbind()
        except:
            pass

    def get_dn_by_username(username):
        return "cn{0},{1}".format(username, self.user_base_dn)

    def get_dn_by_groupname(groupname):
        return "cn{0},{1}".format(groupname, self.group_base_dn)

    def create_user(self, username, password):
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

        if type(username) is not str || type(password) is not str:
            raise ValueError("Username and Password must be strings")

        try:
            open_connection()

            dn = get_dn_by_username(username)

            add_record = [
                ('objectclass', ['person', 'organizationalperson', 'inetorgperson', 'posixAccount', 'top']),
                ('uid', [username]),
                ('uidNumber', ['2550']),
                ('gidNumber', ['2550']),
                ('cn', [username]),
                ('sn', [username]),
                ('userpassword', [password]),
                ('homedirectory', ['/home/test'])
            ]
            self.conn.add_s(dn, add_record)
        finally:
            close_connection()

    def rename_user(self, username, username_new):
        pass

    def set_user_password(username, new_pw):
        try:
            open_connection()

            dn = get_dn_by_username(username)
            mod_attrs = [(ldap.MOD_REPLACE, 'userpassword', new_pw)]
            self.conn.modify_s(dn, mod_attrs)
        finally:
            close_connection()

    def delete_user(self, username):
        try:
            open_connection()

            dn = get_dn_by_username(username)
            self.conn.delete(dn)
        finally:
            close_connection()

    def add_user_to_group(self, username, groupname):
        pass

    def remove_user_from_group(self, username, groupname):
        pass

    def create_group(self, groupname):
        if type(groupname) is not str:
            raise ValueError("Groupname must be a string")

        try:
            open_connection()

            dn = get_dn_by_groupname(groupname)

            add_record = [
                ('objectclass', ['posixGroup', 'top']),
                ('gidNumber', ['2550']),
                ('cn', [groupname]),
                ('memberUid', '')  # TODO: What goes here?
            ]
            self.conn.add_s(dn, add_record)
        finally:
            close_connection()

    def rename_group(self, groupname, groupname_new):
        pass

    def delete_group(self, groupname):
        # TODO: what to do with users in that group?
        try:
            open_connection()

            dn = get_dn_by_groupname(groupname)
            self.conn.delete(dn)
        finally:
            close_connection()
