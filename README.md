# Gitlab to Gitea migration script.

This script uses the Gitlab and Gitea API's to migrate all data from
Gitlab to Gitea.

This script support migrating the following data:
 - Repositories & Wiki
 - Milestones
 - Labels
 - Issues (no comments)
 - Users
 - Groups
 - Public SSH keys

## Usage
Change items in the config section of the script.

Install all dependencies and use python3 to execute the script.
