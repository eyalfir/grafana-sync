#! /usr/bin/python

import requests
import logging
import json
import kubernetes
import time
import sys
import os
import argparse
from vyper import v as vyper


def dict_equal(d1, d2):
    return json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)

def set_label(obj, labels):
    patch = {'metadata': {'labels': labels}}
    client.patch_namespaced_config_map(obj.metadata.name, obj.metadata.namespace, patch)

def clean_dashboard_object(obj):
    for k in ['uid', 'version', 'id']:
        if k in obj:
            del obj[k]

def post(dashboard, uid=None):
    body = json.loads(dashboard.data['json'])
    clean_dashboard_object(body)
    post_obj = {
      "dashboard": body,
      "folderUid": dashboard.metadata.labels.get(LABEL_FOLDER_NAME),
      "message": "synced from source code",
      "overwrite": bool(uid)
    }
    if uid:
        body['uid'] = uid
    response = grafana.post(GRAFANA + '/api/dashboards/db', headers={'Authorization': 'Bearer %s' % API_KEY, 'Content-Type': 'application/json'}, json=post_obj)
    response.raise_for_status()
    set_label(dashboard, {LABEL_VERSION: str(response.json()['version']), LABEL_UID: response.json()['uid']})
    return response.json()['version']

def get_dashboard(uid):
    response = grafana.get(GRAFANA + '/api/dashboards/uid/%s' % uid)
    response.raise_for_status()
    return response.json()

def handle_dashboard(dashboard):
    uid = dashboard.metadata.labels.get(LABEL_UID)
    if not uid:
        try:
            post(dashboard)
            logging.info('successfully synced %s/%s' % (dashboard.metadata.namespace, dashboard.metadata.name))
        except Exception as e:
            logging.exception(e)
            return False
    else:
        existing_dashboard = get_dashboard(uid)
        last_synced_version = int(dashboard.metadata.labels[LABEL_VERSION])
        actual_version = existing_dashboard['dashboard']['version']
        content_spec = json.loads(dashboard.data['json'])
        clean_dashboard_object(existing_dashboard['dashboard'])
        clean_dashboard_object(content_spec)
        if last_synced_version == actual_version:

            if dict_equal(content_spec, existing_dashboard['dashboard']):
                logging.debug('dashboard %s/%s is identical to actual, no need to update' % (dashboard.metadata.namespace, dashboard.metadata.name))
                return
            else:
                new_version = post(dashboard, uid)
                logging.info('dashboard %s/%s has been updated. new version is %s' % (dashboard.metadata.namespace, dashboard.metadata.name, new_version))
        else:
            logging.info('for dashboard %s/%s, actual is ahead, pulling from actual ' % (dashboard.metadata.namespace, dashboard.metadata.name))
            client.patch_namespaced_config_map(dashboard.metadata.name, dashboard.metadata.namespace, {'data': {'json': json.dumps(existing_dashboard['dashboard'], sort_keys=True, indent=2)}})
            set_label(dashboard, {LABEL_VERSION: str(actual_version)})

def sync():
    all_dashboards = client.list_config_map_for_all_namespaces(label_selector='%s=true' % LABEL_SYNC).items
    for dashboard in all_dashboards:
        handle_dashboard(dashboard)
def sync_loop():
    while True:
        sync()
        time.sleep(5)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description="Application settings")
    p.add_argument('--debug', action='store_true')
    p.add_argument('--grafana_url', type=str)
    p.add_argument('--api_key', type=str)
    p.add_argument('--label_prefix', type=str, default='grafana-sync')
    vyper.bind_args(p)
    vyper.set_env_prefix('GRAFANA_SYNC')
    vyper.automatic_env()
    logging.basicConfig(stream=sys.stdout, encoding='utf-8', level=logging.DEBUG if vyper.get('debug') else logging.INFO)
    GRAFANA = vyper.get('grafana_url')
    API_KEY = vyper.get('api_key')
    LABEL_PREFIX = "grafana-sync"
    LABEL_SYNC = "%s.sync" % LABEL_PREFIX
    LABEL_FOLDER_NAME = "%s.folder" % LABEL_PREFIX
    LABEL_UID = "%s.uid" % LABEL_PREFIX
    LABEL_VERSION = '%s.last_synced_version' % LABEL_PREFIX
    try:
        kubernetes.config.load_incluster_config()
    except kubernetes.config.ConfigException:
        try:
            kubernetes.config.load_kube_config()
        except kubernetes.config.ConfigException:
            raise Exception("Could not configure kubernetes python client")
    client = kubernetes.client.CoreV1Api()
    grafana = requests.Session()
    grafana.headers.update({'Content-Type': 'application/json', 'Authorization': 'Bearer %s' % API_KEY})
    s = logging.getLogger('kubernetes.client.rest')
    s.setLevel(logging.INFO)
    sync_loop()
