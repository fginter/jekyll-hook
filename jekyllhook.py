import os
import json
import subprocess
import smtplib
import logging
import git

from time import strftime
from glob import glob

from email.mime.text import MIMEText

from flask import Flask
from flask import request
import os.path

from config import PORT, LOG_DIR, EMAIL_SENDER, EMAIL_RECEIVER, SCRIPT_DIR, SMTP_SERVER, LISTEN_BRANCHES

THISDIR=os.path.dirname(os.path.abspath(__name__))

### CONFIG
# General config is in config.py
# local values (email addresses and smtp server): create config_site.py and set them there. Don't push this file into git.


# Warning: never leave DEBUG = True when deploying: this flag is
# propagated to Flask app debug, which can allow for arbitrary code
# execution.
DEBUG = False

# configure logging
if DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)
else:
    logging.getLogger().setLevel(logging.INFO)
logging.basicConfig(format='%(asctime)s:%(levelname)s:%(funcName)s: %(message)s')

app = Flask(__name__)

def log_event(s):
    if LOG_DIR is None:
        return None

    # assure that LOG_DIR exists
    try:
        os.mkdir(LOG_DIR)
    except OSError:
        pass

    # derive filename from time
    t = strftime("%Y%m%d%H%M%S")
    fn = os.path.join(LOG_DIR, t+'.json')

    try:
        with open(fn, 'wt') as f:
            f.write(s)
    except Exception, e:
        logging.error('failed to write {}: {}', fn, e)

    return fn

def mail_file(fn, subject, sender=EMAIL_SENDER, receiver=EMAIL_RECEIVER):
    if fn is None or sender is None:
        return None

    with open(fn, 'rb') as f:
        msg = MIMEText(f.read())

    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver

    s = smtplib.SMTP(SMTP_SERVER)
    s.sendmail(sender, [receiver], msg.as_string())
    s.quit()

def email_warn(subject,additional_info,event,sender,receivers):
    msg_txt='Committer: "%s" <%s>\nCommit URL: %s\n%s'%(event["head_commit"]["author"]["name"],event["head_commit"]["author"]["email"],event["head_commit"]["url"],additional_info)
    msg=MIMEText(msg_txt)
    msg['Subject']=subject
    msg['From'] = sender
    msg['To'] = ", ".join(receivers)
    s = smtplib.SMTP(SMTP_SERVER)
    s.sendmail(sender, receivers, msg.as_string())
    s.quit()
    

def commit_author(data):
    try:
        return data['commits'][0]['author']['name']
    except Exception:
        return None

def send_email(fn, data):
    author = commit_author(data)
    if author is None:
        subject = 'Jekyll-hook: event'
    else:
        subject = 'Jekyll-hook: commit by {}'.format(author)
    mail_file(fn, subject)

def pretty_print_json(data):
    return json.dumps(data, sort_keys=True, indent=4, separators=(',', ': '))

def load_json(source):
    try:
        data = json.loads(source)
    except Exception, e:
        logging.error('failed to load json from {}: {}'.format(source, e))
        raise
    return data

def run_script(script):
    """script: list of arguments"""
    script_txt=u" ".join(script)
    logging.info('running {}'.format(script_txt))
    try:
        p = subprocess.Popen(script, stdout=subprocess.PIPE, 
                             stderr=subprocess.PIPE)
        out, err = p.communicate() 
    except Exception, e:
        logging.error('failed to run {}: {}'.format(script_txt, e))
        raise

    if out:
        logging.info('{}:OUT: {}'.format(script_txt, out))
    if err:
        logging.error('{}:ERR: {}'.format(script_txt, err))

    logging.info('completed {}'.format(script_txt))

def run_scripts(script_cats,args=[],directory=SCRIPT_DIR):
    if directory is None:
        return None

    scripts = sorted(glob(os.path.join(directory, '*.sh')))

    for script in scripts:
        for c in script_cats:
            if c in script:
                run_script([script]+args)
                break

def get_repo_branch(event):
    branch_name=event["ref"].split("/")[-1] #Hopefully?
    repo_name=event["repository"]["name"]
    return branch_name,repo_name

def warn_on_push_to_branch(event):
    """
    Will send email whenever a push to a certain branch is detected.
    """
    branch_name,repo_name=get_repo_branch(event)
    if branch_name=="master" and repo_name.startswith("UD_"):
        #We have a push into the master branch! WARN!
        email_warn("[UDWARN] Push into master branch of %s"%repo_name,"",event,EMAIL_SENDER,[EMAIL_RECEIVER])
        return True
    return False

def react_on_devel_push(event):
    """
    Will react on a push to a devel branch of a UD_ repo
    """
    # What is the branch of the push and does it match the branch we use as devel for this language?
    branch_name,repo_name=get_repo_branch(event)
    if not repo_name.startswith("UD_"): #only react on UD_ repos
        return False
    repo=git.Repo(os.path.join(THISDIR,"UD-dev-branches",repo_name))
    dev_branch_name=repo.active_branch.name
    if dev_branch_name==branch_name: #We have a push to the branch of interest, must react
        repo.remote("origin").pull()
        logging.info("Push to dev")
        email_warn("[UDINFO] Push into the development branch (%s) branch of %s"%(branch_name,repo_name),"",event,EMAIL_SENDER,[EMAIL_RECEIVER])
        return True
    else:
        return False

#This is a hook which reacts on the project level
@app.route('/', methods=['POST'])
def project_event():
    data = load_json(request.data)

    if warn_on_push_to_branch(data):
        logging.info("Push to master, warned")
        

    # if data["ref"] not in LISTEN_BRANCHES:
    #     #This is probably the gh-pages push resulting from the previous run of this script, ignore
    #     logging.info("Ignoring push on branch %s"%str(data["ref"]))
    #     return "OK"
    
    # fn = log_event(pretty_print_json(data))

    # #Check whether we want to have any specific args
    # scripts=set()
    # args=[]
    # if any(commit["added"]+commit["removed"]+[mod for mod in commit["modified"] if "_data" in mod] for commit in data["commits"]):
    #     logging.info("Detected added/removed files, will run all scripts with --full-rebuild")
    #     args.append("--full-rebuild")
    #     scripts.add("deploy")
    # if any([mod for mod in commit["modified"] if "stests.yaml" in mod or "syn_validation_run.py" in mod] for commit in data["commits"]):
    #     scripts.add("svalid")
    # if any([mod for mod in commit["modified"] if not("stests.yaml" in mod or "syn_validation_run.py" in mod)] for commit in data["commits"]):
    #     scripts.add("deploy")
    # run_scripts(scripts,args=args)

    # send_email(fn, data)

    return "OK"

if __name__ == '__main__':
    # if DEBUG:
    #     app.debug = True
    # app.run(host='0.0.0.0', port=PORT)

#    j=json.loads(open("test.json","rt").read().strip())
#    warn_on_push_to_branch(j)
    
    j=json.loads(open("test.json","rt").read().strip())
    react_on_devel_push(j)

    
