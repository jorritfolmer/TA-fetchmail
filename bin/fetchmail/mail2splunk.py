import os
import ssl
import email
import json
from collections import OrderedDict
from imapclient import IMAPClient

# Copyright 2019 Jorrit Folmer
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


class Mail2Splunk:
    """ This class:
        - gets text/html parts from message bodies
        - and writes then as events to Splunk
    """


    def __init__(self, helper, ew, opt_imap_server, opt_use_ssl, opt_global_account, opt_imap_mailbox, opt_subject, opt_batch_size):
        # Instance variables:
        self.helper             = helper
        self.ew                 = ew
        self.opt_imap_server    = opt_imap_server
        self.opt_imap_mailbox   = 'INBOX' if opt_imap_mailbox == None else opt_imap_mailbox
        self.opt_use_ssl        = opt_use_ssl
        self.opt_global_account = opt_global_account
        self.opt_subject        = opt_subject
        self.opt_batch_size     = 100 if opt_batch_size == None else opt_batch_size
        self.server             = None


    def get_imap_connectivity(self):
        """ Connect to imap server and close the connection """
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_NONE
        try:
            if self.opt_use_ssl:
                self.server=IMAPClient(self.opt_imap_server, use_uid=True, ssl=True, ssl_context=context)
            else:
                self.server=IMAPClient(self.opt_imap_server, use_uid=True, ssl=False)
        except Exception, e:
            raise Exception("Error connecting to %s with exception %s" % (self.opt_imap_server, str(e)))
        else:
            self.helper.log_debug('get_imap_connectivity: successfully connected to %s' % self.opt_imap_server)
 

    def get_messages(self, subject):
        """ Connect to imap server and return a list of msg uids that match the subject """
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.verify_mode = ssl.CERT_NONE
        messages = []
        try:
            if self.opt_use_ssl:
                self.server=IMAPClient(self.opt_imap_server, use_uid=True, ssl=True, ssl_context=context)
            else:
                self.server=IMAPClient(self.opt_imap_server, use_uid=True, ssl=False)
        except Exception, e:
            raise Exception("Error connecting to %s with exception %s" % (self.opt_imap_server, str(e)))
        else:
            self.helper.log_debug('get_messages: successfully connected to %s' % self.opt_imap_server)
            self.server.login(self.opt_global_account["username"], self.opt_global_account["password"])
            info = self.server.select_folder(self.opt_imap_mailbox)
            self.helper.log_info('get_messages: %d messages in folder %s' % (info['EXISTS'], self.opt_imap_mailbox))
            messages = self.server.search('SUBJECT "%s"' % subject)
            self.helper.log_info('get_messages: %d messages in folder %s match subject "%s"' % (len(messages), self.opt_imap_mailbox, subject))
        return messages


    def save_check_point(self, uid, msg):
        """ Save checkpointing info for a given uid and msg struct """
        key = "%s_%s_%d" % (self.opt_imap_server, self.opt_global_account["username"], uid)
        date = email.utils.mktime_tz(email.utils.parsedate_tz(msg.get('Date')))
        value = "input=fetchmail_imap, server=%s, username=%s, uid=%d, timestamp_utc=%d, subject='%s'" % (self.opt_imap_server, self.opt_global_account["username"], uid, date, msg.get('Subject'))
        try:
            self.helper.save_check_point(key, value)
        except Exception, e:
            raise Exception("Error saving checkpoint data with with exception %s" % str(e))


    def filter_seen_messages(self, messages):
        """ From a given list of uids, return only the ones we haven't seen before 
            based on the presence of a KVstore key.
            This key takes into account: imap server, imap account and imap msg uid
        """
        seen_uids = set()
        for uid in messages:
            key = "%s_%s_%d" % (self.opt_imap_server, self.opt_global_account["username"], uid)
            if self.helper.get_check_point(key) != None:
                seen_uids.add(uid)
        new_uids = set(messages) - seen_uids
        self.helper.log_debug('filter_seen_messages: uids on imap   %s' % set(messages))
        self.helper.log_debug('filter_seen_messages: uids in checkp %s' % seen_uids)
        self.helper.log_debug('filter_seen_messages: uids new       %s' % new_uids)
        return new_uids

    def process_incoming(self):
        """ Main function """
        self.helper.log_info("Start processing imap server %s with use_ssl %s" % (self.opt_imap_server, self.opt_use_ssl))
        uids = self.get_messages(self.opt_subject)
        new_uids = self.filter_seen_messages(uids)
        self.helper.log_info('Start processing %d new messages of %d on %s' % ( len(new_uids), len(uids), self.opt_imap_server))
        for new_uid in new_uids:
            response = self.server.fetch(new_uid, ['RFC822'])
            raw_msg = response.get(new_uid)['RFC822']
            msg = email.message_from_string(raw_msg)
            i = 0
            splunk_mail = OrderedDict()
            splunk_mail['date'] = msg.get("date")
            splunk_mail['from'] = msg.get("from")
            splunk_mail['to'] = msg.get("to")
            splunk_mail['subject'] = msg.get("subject")
            for part in msg.walk():
                self.helper.log_debug("uid %d part %d is type %s" % (new_uid, i, part.get_content_type()))
                if part.get_content_type() == "text/html":
                    splunk_mail['body'] = part.get_payload(decode=True)
                    break
                i = i + 1
            event = self.helper.new_event(json.dumps(splunk_mail, indent=2), time=None, host=self.opt_imap_server, index=self.helper.get_output_index(),
                                          source=None, sourcetype="fetchmail:imap:html",
                                          done=True, unbroken=True)
            self.ew.write_event(event)
        self.helper.log_info('Ended processing %d new messages' % len(new_uids))


