# -*- coding: utf-8 -*-

import asyncio
import aiohttp
import copy
import datetime
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
    headers = API_HEADERS
    data = {'password': PASS}
    headers.update({'Content-Length': str(len(str(data))) })
    # print(url, data)
    session = aiohttp.ClientSession(headers=headers)

    async with session.put(url, json=data, timeout=5) as rsp:
        config = await rsp.json()

    if config['meta']['status'] != 'OK':
        print('[%s] Error auth for : %s' % (phone, config))
        await session.close()
        return None, None
    else:
        print('[%s] Login OK' % phone)
        return session, config


async def get_balanse(session, phone):
    url = API_BALANCE % phone

    async with session.get(url, timeout=5) as rsp:
        res = await rsp.json()

    if res['meta']['status'] != 'OK':
        print('[%s] Error get balance : %s' % (phone, res))
        return None
    else:
        return '%s%s' % (res['balance'], res['currency'])


async def get_price(session, phone):
    url = API_PRICE % phone

    async with session.get(url, timeout=5) as rsp:
        res = await rsp.json()

    if res['meta']['status'] != 'OK':
        print('[%s] Error get price : %s' % (phone, res))
    else:
        plan = res['pricePlanInfo']
        return '%s\t%s\t%s' % (plan['entityName'], plan['rcRate'], plan['rcRatePeriodText'])


async def wrk(config, tel):
    await LOCK.acquire()

    if config.get(tel) is None:
        print('[%s] Use auth metod' % tel)
        session, cfg = await login(tel)
        if cfg is None:
            return
        session.cookie_jar.update_cookies({'token': cfg['token']},
                                          response_url=aiohttp.cookiejar.URL('https://my.beeline.ru/'))
        config.update({tel: copy.deepcopy(session.cookie_jar._cookies)})
        await session.close()
    else:
        print('[%s] Use saved data' % tel)

    cookies = config[tel]
    session = aiohttp.ClientSession(headers=API_HEADERS)
    session.cookie_jar._cookies = cookies

    save_config(config)

    try:
        bal = await get_balanse(session, tel)
        price = await get_price(session, tel)
        write_log('%s\t%s\t%s' % (tel, bal,price))
        await session.close()
    except Exception as e:
        await session.close()
        print(e)

    LOCK.release()


if __name__ == '__main__':

    if len(sys.argv) < 3:
        print('beeline.py spisok_telephonov.txt num_threads\n\nSpisok nomerov dolzhen soderzhat 10 tsifr! (primer 9641234567)')
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

    for tel in tells:
        tel = tel.strip()
        futures.append(wrk(config, tel))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.gather(*futures))
    loop.close()
