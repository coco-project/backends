from ipynbsrv.conf import global_vars
from ipynbsrv.backends.usergroup_backends import Ldap
from ipynbsrv.contract.backends import AuthenticationBackend
from ipynbsrv.core.models import IpynbUser
from django.contrib.auth.models import User


# TODO: make dynamic
class LdapAuthentication(AuthenticationBackend):
    def authenticate(self, username=None, password=None):

        # 1. check login credentials
        default = global_vars._get_user_group_backend()
        # default = Ldap('localhost', 'cn=admin,dc=ipynbsrv,dc=ldap', '1234')
        try:
            print("connect {0}@{1} mit {2}".format(username, default.server, password))
            l = Ldap(default.server, default.get_dn_by_username(username), password)
            l.open_connection()
            l.close_connection()
        except:
            print("Error while authenticating")
            return None

        # 2. get Django user
        try:
            ipynbuser = IpynbUser.objects.get(identifier=username)
            print("ipynbuser exists {0}".format(ipynbuser.identifier))
            ipynbuser.user.username = username
            ipynbuser.user.save()
        except IpynbUser.DoesNotExist:
            # Create a new user. Note that we can set password
            # to anything, because it won't be checked;
            try:
                print("ipynbuser does not exist {0}".format(username))
                ldap_user = default.get_user(username)
                print("ldap lookup: {0}".format(ldap_user))
                ipynbuser = IpynbUser(identifier=username, home_directory=ldap_user['homeDirectory'][0])
                print("ipynbuser obj: {0}".format(ipynbuser))
                user = User(username=username)
                user.is_staff = False
                user.is_superuser = False
                print("user obj: {0}".format(user))
                user.save()
                ipynbuser.user = User.objects.get(username=username)
                ipynbuser.save()
            except Exception as e:
                print("not able to create ipynbuser, authentication failed")
                print(e)
                return None
        u = User.objects.get(username=username)
        print("return {0}".format(str(u)))
        return u

    def get_user(self, user_id):
        try:
            print("get user {}".format(user_id))
            u = User.objects.get(pk=user_id)
            # check if user exists on Ldap
            l = global_vars._get_user_group_backend()
            l.get_user(u.ipynbuser.identifier)
            print("user found {}".format(u))
            return u
        except User.DoesNotExist:
            return None
