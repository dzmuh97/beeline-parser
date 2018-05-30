# -*- coding: utf-8 -*-

import asyncio
import aiohttp
import copy
import datetime
import traceback
import _pickle as pkl
import sys, os

PATH = os.path.abspath(os.path.dirname(sys.argv[0]))
CNF = os.path.join(PATH, 'tokens.dat')
LOG = os.path.join(PATH, 'log.tsv')
PASS = '' # password
API_URL = 'https://my.beeline.ru/api/2.0/auth/auth?userType=Mobile&login=%s'
API_BALANCE = 'https://my.beeline.ru/api/1.0/info/prepaidBalance?ctn=%s'
API_PRICE = 'https://my.beeline.ru/api/1.0/info/pricePlan?ctn=%s'
API_HEADERS = {
    'User-Agent': 'okhttp/2.6.0',
    'Client-Type': 'MYBEE/ANDROID/PHONE/2.90',
    'Content-Type': 'application/json; charset=UTF-8',
    'Accept-Encoding': 'gzip,deflate',
    'Host': 'my.beeline.ru',
    'Connection': 'Keep-Alive',
    'Cookie': '',
    'Cookie2': '$Version=1'
}

LOCK = asyncio.Semaphore()


def parse_config():
    if os.path.exists(CNF):
        return pkl.load(open(CNF, 'rb'))
    else:
        return {}


def save_config(config):
    if not os.path.exists(CNF):
        open(CNF, 'wb').close()
    pkl.dump(config, open(CNF, 'wb'))


def write_log(data):
    if not os.path.exists(LOG):
        log = open(LOG, 'w')
    else:
        log = open(LOG, 'a')
    log.write(data + '\n')


async def login(phone):

    url = API_URL % phone
    headers = copy.deepcopy(API_HEADERS)
    data = {'password': PASS}
    headers.update({'Content-Length': str(len(str(data))) })
    # print(url, data)
    session = aiohttp.ClientSession(headers=headers)

    async with session.put(url, json=data, timeout=15) as rsp:
        config = await rsp.json()

    if config['meta']['status'] != 'OK':
        print('[%s] Error auth for : %s' % (phone, config))
        await session.close()
        return None, None
    else:
        print('[%s] Login OK' % phone)
        return session, {'token': 'token=%s' % config['token'], 'srv': rsp.headers['Set-Cookie'].split(';')[0]}


async def get_balanse(session, phone):
    url = API_BALANCE % phone

    async with session.get(url, timeout=15) as rsp:
        res = await rsp.json()

    if res['meta']['status'] != 'OK':
        print('[%s] Error get balance : %s' % (phone, res))
        return None
    else:
        return '%s%s' % (res.get('balance', 'NULL'),
                         res.get('currency', 'NULL'))


async def get_price(session, phone):
    url = API_PRICE % phone

    async with session.get(url, timeout=15) as rsp:
        res = await rsp.json()

    if res['meta']['status'] != 'OK':
        print('[%s] Error get price : %s' % (phone, res))
    else:
        plan = res['pricePlanInfo']
        return '%s\t%s\t%s' % (plan.get('entityName', 'NULL'),
                               plan.get('rcRate', 'NULL'),
                               plan.get('rcRatePeriodText', 'NULL'))


async def wrk(config, tel):
    await LOCK.acquire()

    if config.get(tel) is None:
        print('[%s] Use auth method' % tel)
        session, cfg = await login(tel)
        if cfg is None:
            LOCK.release()
            return
        config.update({tel: cfg})
        await session.close()
    else:
        print('[%s] Use saved data' % tel)

    conf = config[tel]
    headers = copy.deepcopy(API_HEADERS)
    headers['Cookie'] = '%s; %s' % (conf['srv'], conf['token'])
    session = aiohttp.ClientSession(headers=headers)

    save_config(config)

    try:
        bal = await get_balanse(session, tel)
        price = await get_price(session, tel)
        write_log('%s\t%s\t%s' % (tel, bal,price))
        print('[%s] Data OK' % tel)
        await session.close()
    except:
        await session.close()
        print('[%s] Error: %s' % (tel, traceback.format_exc()))

    LOCK.release()


if __name__ == '__main__':

    if len(sys.argv) < 3:
        print('beeline.py spisok_telephonov.txt num_threads\n\nSpisok nomerov dolzhen soderzhat tolko 10 tsifr!')
        exit()

    telsp = sys.argv[1]
    ths = int(sys.argv[2])

    if ths != 1:
        LOCK = asyncio.Semaphore(ths)

    now = datetime.datetime.now()
    write_log('----- %s -----' % now)

    sp = os.path.join(PATH, telsp)
    tells = open(sp, 'r').readlines()
    config = parse_config()
    futures = []

    loop = asyncio.get_event_loop()

    for tel in tells:

        _tel = ''
        for q in tel:
            if q in '0123456789':
                _tel += q
        tel = _tel

        if not tel:
            continue
        task = loop.create_task(wrk(config, tel))
        futures.append(task)

    print('Loaded %d nums.' % len(futures))

    wait_tasks = asyncio.wait(futures)
    loop.run_until_complete(wait_tasks)
    loop.close()
