# Gitlab to Gitea migration script.

This script uses the Gitlab and Gitea API's to migrate all data from
Gitlab to Gitea.

This script support migrating the following data:
 - Repositories & Wiki (fork status is lost)
 - Milestones
 - Labels
 - Issues (no comments)
 - Users (no profile pictures)
 - Groups
 - Public SSH keys

Tested with Gitlab Version 13.0.6 and Gitea Version 1.11.6.

## Usage
Change items in the config section of the script.

Install all dependencies via `python -m pip install -r requirements.txt` and
use python3 to execute the script.

### How to use with venv
To keep your local system clean, it might be helpful to store all Python dependencies in one folder.
Python provides a virtual environment package which can be used to accomplish this task.

```bash
python3 -m venv migration-env
source migration-env/bin/activate
python3 -m pip install -r requirements.txt
```

Then start the migration script `python3 migrate.py`.

1、edit migrate.py  
```bash
# gitlab 
GITLAB_URL = os.getenv('GITLAB_URL', 'https://gitlab.source.com')
GITLAB_TOKEN = os.getenv('GITLAB_TOKEN', 'gitlab token')

# needed to clone the repositories, keep empty to try publickey (untested)
GITLAB_ADMIN_USER = os.getenv('GITLAB_ADMIN_USER', 'admin username')
GITLAB_ADMIN_PASS = os.getenv('GITLAB_ADMIN_PASS', 'admin password')

# gitea
GITEA_URL = os.getenv('GITEA_URL','https://gitea.dest.com')
GITEA_TOKEN = os.getenv('GITEA_TOKEN', 'gitea token')
```

2、Test Gitea migrate api
url:
http://192.168.50.203:3000/api/v1/repos/migrate?access_token=bac1a114d441a31ae812c8aa2f4002eb89466388

method:
POST

header:  
[{"key":"Content-Type","value":"application/json"}]

Data:
{
  "auth_password": "gitlab password",
  "auth_token": "gitlab token",
  "auth_username": "root",
  "clone_addr": "clone_addr gitlab addr",
  "description": "1222222",
  "issues": false,
  "labels": false,
  "lfs": false,
  "milestones": false,
  "mirror": false,
  "private": true,
  "pull_requests": false,
  "releases": true,
  "repo_name": "test1",
  "repo_owner": "root",
  "service": "git",
  "uid": 1,
  "wiki": true
}
