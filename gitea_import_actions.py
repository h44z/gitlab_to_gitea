# Import commits to gitea action database.
# use:
# git log --pretty=format:'%H,%at,%s' --date=default > /tmp/commit.log
# to get the commits logfile for a repository

import mysql.connector as mariadb

# set the following variables to fit your need...
USERID = 1
REPOID = 1
BRANCH = "master"

mydb = mariadb.connect(
  host="localhost",
  user="user",
  passwd="password",
  database="gitea"
)

mycursor = mydb.cursor()

sql = "INSERT INTO action (user_id, op_type, act_user_id, repo_id, comment_id, ref_name, is_private, created_unix) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"

with open("/tmp/commit.log") as f:
    for line in f:
        line_clean = line.rstrip('\n')
        line_split = line_clean.split(',')
        val = (USERID, 5, USERID, REPOID, 0, BRANCH, 1, int(line_split[1]))  # 5 means commit
        print(val)
        mycursor.execute(sql, val)

mydb.commit()

print("actions inserted.")