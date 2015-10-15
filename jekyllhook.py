import os
import json
import subprocess
import smtplib
import logging

from time import strftime
from glob import glob

from email.mime.text import MIMEText

from flask import Flask
from flask import request

from config import PORT, LOG_DIR, EMAIL_SENDER, EMAIL_RECEIVER, SCRIPT_DIR, SMTP_SERVER, LISTEN_BRANCHES


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

def run_scripts(args=[],directory=SCRIPT_DIR):
    if directory is None:
        return None

    scripts = glob(os.path.join(directory, '*.sh'))

    for script in scripts:
        run_script([script]+args)

@app.route('/', methods=['POST'])
def event():
    data = load_json(request.data)

    if data["ref"] not in LISTEN_BRANCHES:
        #This is probably the gh-pages push resulting from the previous run of this script, ignore
        logging.info("Ignoring push on branch %s"%str(data["ref"]))
        return "OK"
    
    fn = log_event(pretty_print_json(data))

    #Check whether we want to have any specific args
    args=[]
    if any(commit["added"]+commit["removed"]+[mod for mod in commit["modified"] if "_data" in mod] for commit in data["commits"]):
        logging.info("Detected added/removed files, will run all scripts with --full-rebuild")
        args.append("--full-rebuild")

    run_scripts(args=args)

    send_email(fn, data)

    return "OK"

if __name__ == '__main__':
    if DEBUG:
        app.debug = True
    app.run(host='0.0.0.0', port=PORT)
