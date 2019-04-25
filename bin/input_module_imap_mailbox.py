# encoding = utf-8

import os
import sys
import time
import datetime
from fetchmail.mail2splunk import Mail2Splunk


'''
    IMPORTANT
    Edit only the validate_input and collect_events functions.
    Do not edit any other part in this file.
    This file is generated only once when creating the modular input.
'''
'''
# For advanced users, if you want to create single instance mod input, uncomment this method.
def use_single_instance_mode():
    return True
'''

def validate_input(helper, definition):
    """Implement your own validation logic to validate the input stanza configurations"""
    # This example accesses the modular input variable
    # imap_server = definition.parameters.get('imap_server', None)
    # global_account = definition.parameters.get('global_account', None)
    pass

def collect_events(helper, ew):
    opt_imap_server    = helper.get_arg("imap_server")
    opt_imap_mailbox   = helper.get_arg("imap_mailbox")
    opt_use_ssl        = True
    opt_global_account = helper.get_arg('global_account')
    opt_batch_size     = int(helper.get_arg('batch_size'))
    opt_subject        = helper.get_arg('subject_filter')

    loglevel   = helper.get_log_level()
    helper.set_log_level(loglevel)

    m2s = Mail2Splunk(helper, ew, opt_imap_server, opt_use_ssl, opt_global_account, opt_imap_mailbox, opt_subject, opt_batch_size)
    try:
        m2s.process_incoming()
    finally:
        pass

