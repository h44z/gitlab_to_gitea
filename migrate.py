import base64
import os
import time
import random
import string
import requests
import json
import dateutil.parser
import datetime
import re

import gitlab  # pip install python-gitlab
import gitlab.v4.objects
import pygitea # pip install pygitea (https://github.com/h44z/pygitea)

SCRIPT_VERSION = "1.0"
GLOBAL_ERROR_COUNT = 0

#######################
# CONFIG SECTION START
#######################
GITLAB_URL = os.getenv('GITLAB_URL', 'https://gitlab.source.com')
GITLAB_TOKEN = os.getenv('GITLAB_TOKEN', 'gitlab token')

# needed to clone the repositories, keep empty to try publickey (untested)
GITLAB_ADMIN_USER = os.getenv('GITLAB_ADMIN_USER', 'admin username')
GITLAB_ADMIN_PASS = os.getenv('GITLAB_ADMIN_PASS', 'admin password')

GITEA_URL = os.getenv('GITEA_URL','https://gitea.dest.com')
GITEA_TOKEN = os.getenv('GITEA_TOKEN', 'gitea token')
#######################
# CONFIG SECTION END
#######################


def main():
    print_color(bcolors.HEADER, "---=== Gitlab to Gitea migration ===---")
    print("Version: " + SCRIPT_VERSION)
    print()

    # private token or personal token authentication
    gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
    gl.auth()
    assert(isinstance(gl.user, gitlab.v4.objects.CurrentUser))
    print_info("Connected to Gitlab, version: " + str(gl.version()))

    gt = pygitea.API(GITEA_URL, token=GITEA_TOKEN)
    gt_version = gt.get('/version').json()
    print_info("Connected to Gitea, version: " + str(gt_version['version']))

    # IMPORT USERS AND GROUPS
    import_users_groups(gl, gt)

    # IMPORT PROJECTS
    import_projects(gl, gt)

    print()
    if GLOBAL_ERROR_COUNT == 0:
        print_success("Migration finished with no errors!")
    else:
        print_error("Migration finished with " + str(GLOBAL_ERROR_COUNT) + " errors!")


# 
# Data loading helpers for Gitea
#

def get_labels(gitea_api: pygitea, owner: string, repo: string) -> []:
    existing_labels = []
    label_response: requests.Response = gitea_api.get("/repos/" + owner + "/" + repo + "/labels")
    if label_response.ok:
        existing_labels = label_response.json()
    else:
        print_error("Failed to load existing milestones for project " + repo + "! " + label_response.text)

    return existing_labels


def get_milestones(gitea_api: pygitea, owner: string, repo: string) -> []:
    existing_milestones = []
    milestone_response: requests.Response = gitea_api.get("/repos/" + owner + "/" + repo + "/milestones")
    if milestone_response.ok:
        existing_milestones = milestone_response.json()
    else:
        print_error("Failed to load existing milestones for project " + repo + "! " + milestone_response.text)

    return existing_milestones


def get_issues(gitea_api: pygitea, owner: string, repo: string) -> []:
    existing_issues = []
    issue_response: requests.Response = gitea_api.get("/repos/" + owner + "/" + repo + "/issues", params={
        "state": "all",
        "page": -1
    })
    if issue_response.ok:
        existing_issues = issue_response.json()
    else:
        print_error("Failed to load existing issues for project " + repo + "! " + issue_response.text)

    return existing_issues


def get_teams(gitea_api: pygitea, orgname: string) -> []:
    existing_teams = []
    team_response: requests.Response = gitea_api.get("/orgs/" + orgname + "/teams")
    if team_response.ok:
        existing_teams = team_response.json()
    else:
        print_error("Failed to load existing teams for organization " + orgname + "! " + team_response.text)

    return existing_teams


def get_team_members(gitea_api: pygitea, teamid: int) -> []:
    existing_members = []
    member_response: requests.Response = gitea_api.get("/teams/" + str(teamid) + "/members")
    if member_response.ok:
        existing_members = member_response.json()
    else:
        print_error("Failed to load existing members for team " + str(teamid) + "! " + member_response.text)

    return existing_members


def get_collaborators(gitea_api: pygitea, owner: string, repo: string) -> []:
    existing_collaborators = []
    collaborator_response: requests.Response = gitea_api.get("/repos/" + owner+ "/" + repo + "/collaborators")
    if collaborator_response.ok:
        existing_collaborators = collaborator_response.json()
    else:
        print_error("Failed to load existing collaborators for project " + repo + "! " + collaborator_response.text)

    return existing_collaborators


def get_user_or_group(gitea_api: pygitea, project: gitlab.v4.objects.Project) -> {}:
    result = None
    response: requests.Response = gitea_api.get("/users/" + name_clean(project.namespace['path']))
    if response.ok:
        result = response.json()

    # The api may return a 200 response, even if it's not a user but an org, let's try again!
    if result is None or result["id"] == 0:
        response: requests.Response = gitea_api.get("/orgs/" + name_clean(project.namespace["name"]))
        if response.ok:
            result = response.json()
        else:
            print_error("Failed to load user or group " + name_clean(project.namespace["name"]) + "! " + response.text)

    return result


def get_user_keys(gitea_api: pygitea, username: string) -> {}:
    result = []
    key_response: requests.Response = gitea_api.get("/users/" + username + "/keys")
    if key_response.ok:
        result = key_response.json()
    else:
        print_error("Failed to load user keys for user " + username + "! " + key_response.text)

    return result


def user_exists(gitea_api: pygitea, username: string) -> bool:
    user_response: requests.Response = gitea_api.get("/users/" + username)
    if user_response.ok:
        print_warning("User " + username + " does already exist in Gitea, skipping!")
    else:
        print("User " + username + " not found in Gitea, importing!")

    return user_response.ok


def user_key_exists(gitea_api: pygitea, username: string, keyname: string) -> bool:
    existing_keys = get_user_keys(gitea_api, username)
    if existing_keys:
        existing_key = next((item for item in existing_keys if item["title"] == keyname), None)

        if existing_key is not None:
            print_warning("Public key " + keyname + " already exists for user " + username + ", skipping!")
            return True
        else:
            print("Public key " + keyname + " does not exists for user " + username + ", importing!")
            return False
    else:
        print("No public keys for user " + username + ", importing!")
        return False


def organization_exists(gitea_api: pygitea, orgname: string) -> bool:
        group_response: requests.Response = gitea_api.get("/orgs/" + orgname)
        if group_response.ok:
            print_warning("Group " + orgname + " does already exist in Gitea, skipping!")
        else:
            print("Group " + orgname + " not found in Gitea, importing!")

        return group_response.ok


def member_exists(gitea_api: pygitea, username: string, teamid: int) -> bool:
    existing_members = get_team_members(gitea_api, teamid)
    if existing_members:
        existing_member = next((item for item in existing_members if item["username"] == username), None)

        if existing_member:
            print_warning("Member " + username + " is already in team " + str(teamid) + ", skipping!")
            return True
        else:
            print("Member " + username + " is not in team " + str(teamid) + ", importing!")
            return False
    else:
        print("No members in team " + str(teamid) + ", importing!")
        return False


def collaborator_exists(gitea_api: pygitea, owner: string, repo: string, username: string) -> bool:
    collaborator_response: requests.Response = gitea_api.get("/repos/" + owner + "/" + repo + "/collaborators/" + username)
    if collaborator_response.ok:
        print_warning("Collaborator " + username + " does already exist in Gitea, skipping!")
    else:
        print("Collaborator " + username + " not found in Gitea, importing!")

    return collaborator_response.ok


def repo_exists(gitea_api: pygitea, owner: string, repo: string) -> bool:
    repo_response: requests.Response = gitea_api.get("/repos/" + owner + "/" + repo)
    if repo_response.ok:
        print_warning("Project " + repo + " does already exist in Gitea, skipping!")
    else:
        print("Project " + repo + " not found in Gitea, importing!")

    return repo_response.ok


def label_exists(gitea_api: pygitea, owner: string, repo: string, labelname: string) -> bool:
    existing_labels = get_labels(gitea_api, owner, repo)
    if existing_labels:
        existing_label = next((item for item in existing_labels if item["name"] == labelname), None)

        if existing_label is not None:
            print_warning("Label " + labelname + " already exists in project " + repo + ", skipping!")
            return True
        else:
            print("Label " + labelname + " does not exists in project " + repo + ", importing!")
            return False
    else:
        print("No labels in project " + repo + ", importing!")
        return False


def milestone_exists(gitea_api: pygitea, owner: string, repo: string, milestone: string) -> bool:
    existing_milestones = get_milestones(gitea_api, owner, repo)
    if existing_milestones:
        existing_milestone = next((item for item in existing_milestones if item["title"] == milestone), None)

        if existing_milestone is not None:
            print_warning("Milestone " + milestone + " already exists in project " + repo + ", skipping!")
            return True
        else:
            print("Milestone " + milestone + " does not exists in project " + repo + ", importing!")
            return False
    else:
        print("No milestones in project " + repo + ", importing!")
        return False


def issue_exists(gitea_api: pygitea, owner: string, repo: string, issue: string) -> bool:
    existing_issues = get_issues(gitea_api, owner, repo)
    if existing_issues:
        existing_issue = next((item for item in existing_issues if item["title"] == issue), None)

        if existing_issue is not None:
            print_warning("Issue " + issue + " already exists in project " + repo + ", skipping!")
            return True
        else:
            print("Issue " + issue + " does not exists in project " + repo + ", importing!")
            return False
    else:
        print("No issues in project " + repo + ", importing!")
        return False


#
# Import helper functions
#

def _import_project_labels(gitea_api: pygitea, labels: [gitlab.v4.objects.ProjectLabel], owner: string, repo: string):
    for label in labels:
        if not label_exists(gitea_api, owner, repo, label.name):
            import_response: requests.Response = gitea_api.post("/repos/" + owner + "/" + repo + "/labels", json={
                "name": label.name,
                "color": label.color,
                "description": label.description # currently not supported
            })
            if import_response.ok:
                print_info("Label " + label.name + " imported!")
            else:
                print_error("Label " + label.name + " import failed: " + import_response.text)


def _import_project_milestones(gitea_api: pygitea, milestones: [gitlab.v4.objects.ProjectMilestone], owner: string, repo: string):
    for milestone in milestones:
        if not milestone_exists(gitea_api, owner, repo, milestone.title):                    
            due_date = None
            if milestone.due_date is not None and milestone.due_date != '':
                due_date = dateutil.parser.parse(milestone.due_date).strftime('%Y-%m-%dT%H:%M:%SZ')

            import_response: requests.Response = gitea_api.post("/repos/" + owner + "/" + repo + "/milestones", json={
                "description": milestone.description,
                "due_on": due_date,
                "title": milestone.title,
            })
            if import_response.ok:
                print_info("Milestone " + milestone.title + " imported!")
                existing_milestone = import_response.json()

                if existing_milestone:
                    # update milestone state, this cannot be done in the initial import :(
                    # TODO: gitea api ignores the closed state...
                    update_response: requests.Response = gitea_api.patch("/repos/" + owner + "/" + repo + "/milestones/" + str(existing_milestone['id']), json={
                        "description": milestone.description,
                        "due_on": due_date,
                        "title": milestone.title,
                        "state": milestone.state
                    })
                    if update_response.ok:
                        print_info("Milestone " + milestone.title + " updated!")
                    else:
                        print_error("Milestone " + milestone.title + " update failed: " + update_response.text)
            else:
                print_error("Milestone " + milestone.title + " import failed: " + import_response.text)


def _import_project_issues(gitea_api: pygitea, issues: [gitlab.v4.objects.ProjectIssue], owner: string, repo: string):
    # reload all existing milestones and labels, needed for assignment in issues
    existing_milestones = get_milestones(gitea_api, owner, repo)
    existing_labels = get_labels(gitea_api, owner, repo)

    for issue in issues:
        if not issue_exists(gitea_api, owner, repo, issue.title):
            due_date = ''
            if issue.due_date is not None:
                due_date = dateutil.parser.parse(issue.due_date).strftime('%Y-%m-%dT%H:%M:%SZ')
            
            assignee = None
            if issue.assignee is not None:
                assignee = issue.assignee['username']

            assignees = []
            for tmp_assignee in issue.assignees:
                assignees.append(tmp_assignee['username'])

            milestone = None
            if issue.milestone is not None:
                existing_milestone = next((item for item in existing_milestones if item["title"] == issue.milestone['title']), None)
                if existing_milestone:
                    milestone = existing_milestone['id']

            labels = []
            for label in issue.labels:
                existing_label = next((item for item in existing_labels if item["name"] == label), None)
                if existing_label:
                    labels.append(existing_label['id'])

            import_response: requests.Response = gitea_api.post("/repos/" + owner + "/" + repo + "/issues", json={
                "assignee": assignee,
                "assignees": assignees,
                "body": issue.description,
                "closed": issue.state == 'closed',
                "due_on": due_date,
                "labels": labels,
                "milestone": milestone,
                "title": issue.title,
            })
            if import_response.ok:
                print_info("Issue " + issue.title + " imported!")
            else:
                print_error("Issue " + issue.title + " import failed: " + import_response.text)


def _import_project_repo(gitea_api: pygitea, project: gitlab.v4.objects.Project):
    if not repo_exists(gitea_api, name_clean(project.namespace['name']), name_clean(project.name)):
        clone_url = project.http_url_to_repo
        if GITLAB_ADMIN_PASS == '' and GITLAB_ADMIN_USER == '':
            clone_url = project.ssh_url_to_repo
        private = project.visibility == 'private' or project.visibility == 'internal'

        # Load the owner (users and groups can both be fetched using the /users/ endpoint)
        owner = get_user_or_group(gitea_api, project)
        if owner:
            description = project.description

            if description is not None and len(description) > 255:
                description = description[:255]
                print_warning(f"Description of {name_clean(project.name)} had to be truncated to 255 characters!")

            import_response: requests.Response = gitea_api.post("/repos/migrate", json={
                "auth_password": GITLAB_ADMIN_PASS,
                "auth_username": GITLAB_ADMIN_USER,
                "clone_addr": clone_url,
                "description": description,
                "mirror": False,
                "private": private,
                "repo_name": name_clean(project.name),
                "uid": owner['id']
            })
            if import_response.ok:
                print_info("Project " + name_clean(project.name) + " imported!")
            else:
                print_error("Project " + name_clean(project.name) + " import failed: " + import_response.text)
        else:
            print_error("Failed to load project owner for project " + name_clean(project.name))


def _import_project_repo_collaborators(gitea_api: pygitea, collaborators: [gitlab.v4.objects.ProjectMember], project: gitlab.v4.objects.Project):
    for collaborator in collaborators:
        
        if not collaborator_exists(gitea_api, name_clean(project.namespace['name']), name_clean(project.name), collaborator.username):
            permission = "read"
            
            if collaborator.access_level == 10:    # guest access
                permission = "read"
            elif collaborator.access_level == 20:  # reporter access
                permission = "read"
            elif collaborator.access_level == 30:  # developer access
                permission = "write"
            elif collaborator.access_level == 40:  # maintainer access
                permission = "admin"
            elif collaborator.access_level == 50:  # owner access (only for groups)
                print_error("Groupmembers are currently not supported!")
                continue  # groups are not supported
            else:
                print_warning("Unsupported access level " + str(collaborator.access_level) + ", setting permissions to 'read'!")
            
            import_response: requests.Response = gitea_api.put("/repos/" + name_clean(project.namespace['name']) +"/" + name_clean(project.name) + "/collaborators/" + collaborator.username, json={
                "permission": permission
            })
            if import_response.ok:
                print_info("Collaborator " + collaborator.username + " imported!")
            else:
                print_error("Collaborator " + collaborator.username + " import failed: " + import_response.text)


def _import_users(gitea_api: pygitea, users: [gitlab.v4.objects.User], notify: bool = False):
    for user in users:
        keys: [gitlab.v4.objects.UserKey] = user.keys.list(all=True)

        print("Importing user " + user.username + "...")
        print("Found " + str(len(keys)) + " public keys for user " + user.username)

        if not user_exists(gitea_api, user.username):
            tmp_password = 'Tmp1!' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            tmp_email = user.username + '@noemail-git.local'  # Some gitlab instances do not publish user emails
            try:
                tmp_email = user.email
            except AttributeError:
                pass
            import_response: requests.Response = gitea_api.post("/admin/users", json={
                "email": tmp_email,
                "full_name": user.name,
                "login_name": user.username,
                "password": tmp_password,
                "send_notify": notify,
                "source_id": 0, # local user
                "username": user.username
            })
            if import_response.ok:
                print_info("User " + user.username + " imported, temporary password: " + tmp_password)
            else:
                print_error("User " + user.username + " import failed: " + import_response.text)
        
        # import public keys
        _import_user_keys(gitea_api, keys, user)


def _import_user_keys(gitea_api: pygitea, keys: [gitlab.v4.objects.UserKey], user: gitlab.v4.objects.User):
    for key in keys:
        if not user_key_exists(gitea_api, user.username, key.title):
            import_response: requests.Response = gitea_api.post("/admin/users/" + user.username + "/keys", json={
                "key": key.key,
                "read_only": True,
                "title": key.title,
            })
            if import_response.ok:
                print_info("Public key " + key.title + " imported!")
            else:
                print_error("Public key " + key.title + " import failed: " + import_response.text)


def _import_groups(gitea_api: pygitea, groups: [gitlab.v4.objects.Group]):
    for group in groups:
        members: [gitlab.v4.objects.GroupMember] = group.members.list(all=True)

        print("Importing group " + name_clean(group.name) + "...")
        print("Found " + str(len(members)) + " gitlab members for group " + name_clean(group.name))

        if not organization_exists(gitea_api, name_clean(group.name)):
            import_response: requests.Response = gitea_api.post("/orgs", json={
                "description": group.description,
                "full_name": group.full_name,
                "location": "",
                "username": name_clean(group.name),
                "website": ""
            })
            if import_response.ok:
                print_info("Group " + name_clean(group.name) + " imported!")
            else:
                print_error("Group " + name_clean(group.name) + " import failed: " + import_response.text)

        # import group members
        _import_group_members(gitea_api, members, group)


def _import_group_members(gitea_api: pygitea, members: [gitlab.v4.objects.GroupMember], group: gitlab.v4.objects.Group):
    # TODO: create teams based on gitlab permissions (access_level of group member)
    existing_teams = get_teams(gitea_api, name_clean(group.name))
    if existing_teams:
        first_team = existing_teams[0]
        print("Organization teams fetched, importing users to first team: " + first_team['name'])

        # add members to teams
        for member in members:
            if not member_exists(gitea_api, member.username, first_team['id']):
                import_response: requests.Response = gitea_api.put("/teams/" + str(first_team['id']) + "/members/" + member.username)
                if import_response.ok:
                    print_info("Member " + member.username + " added to group " + name_clean(group.name) + "!")
                else:
                    print_error("Failed to add member " + member.username + " to group " + name_clean(group.name) + "!")
    else:
        print_error("Failed to import members to group " + name_clean(group.name) + ": no teams found!")


#
# Import functions
#

def import_users_groups(gitlab_api: gitlab.Gitlab, gitea_api: pygitea, notify=False):
    # read all users
    users: [gitlab.v4.objects.User] = gitlab_api.users.list(all=True)
    groups: [gitlab.v4.objects.Group] = gitlab_api.groups.list(all=True)

    print("Found " + str(len(users)) + " gitlab users as user " + gitlab_api.user.username)
    print("Found " + str(len(groups)) + " gitlab groups as user " + gitlab_api.user.username)

    # import all non existing users
    _import_users(gitea_api, users, notify)

    # import all non existing groups
    _import_groups(gitea_api, groups)


def import_projects(gitlab_api: gitlab.Gitlab, gitea_api: pygitea):
    # read all projects and their issues
    projects: gitlab.v4.objects.Project = gitlab_api.projects.list(all=True)

    print("Found " + str(len(projects)) + " gitlab projects as user " + gitlab_api.user.username)

    for project in projects:
        try:
            collaborators: [gitlab.v4.objects.ProjectMember] = project.members.list(all=True)
            labels: [gitlab.v4.objects.ProjectLabel] = project.labels.list(all=True)
            milestones: [gitlab.v4.objects.ProjectMilestone] = project.milestones.list(all=True)
            issues: [gitlab.v4.objects.ProjectIssue] = project.issues.list(all=True)

            print("Importing project " + name_clean(project.name) + " from owner " + name_clean(project.namespace['name']))
            print("Found " + str(len(collaborators)) + " collaborators for project " + name_clean(project.name))
            print("Found " + str(len(labels)) + " labels for project " + name_clean(project.name))
            print("Found " + str(len(milestones)) + " milestones for project " + name_clean(project.name))
            print("Found " + str(len(issues)) + " issues for project " + name_clean(project.name))

        except Exception as e:
            print("This project failed: \n {}, \n reason {}: ".format(project.name, e))
        
        else:
            projectOwner = name_clean(project.namespace['name'])
            projectName = name_clean(project.name)

            # import project repo
            _import_project_repo(gitea_api, project)

            # import collaborators
            _import_project_repo_collaborators(gitea_api, collaborators, project)

            # import labels
            _import_project_labels(gitea_api, labels, projectOwner, projectName)

            # import milestones
            _import_project_milestones(gitea_api, milestones, projectOwner, projectName)

            # import issues
            _import_project_issues(gitea_api, issues, projectOwner, projectName)


#
# Helper functions
#

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def color_message(color, message, colorend=bcolors.ENDC, bold=False):
    if bold:
        return bcolors.BOLD + color_message(color, message, colorend, False)

    return color + message + colorend

def print_color(color, message, colorend=bcolors.ENDC, bold=False):
    print(color_message(color, message, colorend))


def print_info(message):
    print_color(bcolors.OKBLUE, message)


def print_success(message):
    print_color(bcolors.OKGREEN, message)


def print_warning(message):
    print_color(bcolors.WARNING, message)


def print_error(message):
    global GLOBAL_ERROR_COUNT
    GLOBAL_ERROR_COUNT += 1
    print_color(bcolors.FAIL, message)


def name_clean(name):
    newName = name.replace(" ", "_")
    newName = re.sub(r"[^a-zA-Z0-9_\.-]", "-", newName)

    if (newName.lower() == "plugins"):
        return newName + "-user"
    
    return newName


if __name__ == "__main__":
    main()
