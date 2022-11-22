#!/usr/bin/python3
import sys, os, subprocess
import random, time, requests
import hashlib, glob, base64

# default configurations
SESSION_TIME = 3
BUILD_CACHE_TIMEOUT = 3600.0 * 24 * 7   # 1 week
MASTER_URL = 'http://daehee.kr:7810'

if sys.version_info[0] < 3:
    print("python3 required")
    os._exit(-1)

# check directory permission
if not os.access('.', os.R_OK | os.W_OK):
    print("Read/Write permission required for current directory")
    os._exit(-1)

if subprocess.call(['which', 'git']) != 0:
    print('please install git: "sudo apt install git"')
if subprocess.call(['which', 'docker']) != 0:
    print('please install docker: "sudo apt install docker.io"')
if subprocess.call(['which', 'unzip']) != 0:
    print('please install unzip: "sudo apt install unzip"')

def auth(botid):
    global MASTER_URL
    params = {"botid":botid}
    ret = requests.post(MASTER_URL+'/auth', json=params)
    ret = ret.json()
    if ret['retcode'] != 0:
        print('Authentication Error: %s' % ret['msg'])
        return False
    else:
        return True

def sync_config(botid):
    global MASTER_URL
    global SESSION_TIME
    global BUILD_CACHE_TIMEOUT
    params = {"botid":botid}
    ret = requests.post(MASTER_URL+'/config', json=params)
    ret = ret.json()
    if ret['retcode'] != 0:
        print('Error while syncing configuration: %s' % ret['msg'])
        return False
    else:
        SESSION_TIME = int(ret['SESSION_TIME'])
        BUILD_CACHE_TIMEOUT = float(ret['BUILD_CACHE_TIMEOUT'])
        return True

def getOSSFuzz():
    url = 'https://github.com/google/oss-fuzz'
    if not os.path.isdir('oss-fuzz'):
        os.system('git clone https://github.com/google/oss-fuzz')
    else:
        try:
            os.chdir('oss-fuzz')
            os.system('git pull')
        finally:
            os.chdir('..')
    print("oss-fuzz repo ready, up to date")

def _get_fuzz_targets(project):
    out_dir = 'build/out/%s' % project
    """Returns names of fuzz targest build in the project's /out directory."""
    fuzz_targets = []
    for name in os.listdir(out_dir):
        if name.startswith('afl-'): continue
        if name.startswith('jazzer_'): continue
        if name == 'llvm-symbolizer': continue

        path = os.path.join(out_dir, name)
        # Python and JVM fuzz targets are only executable for the root user, so
        # we can't use os.access.
        if os.path.isfile(path) and (os.stat(path).st_mode & 0o111):
            fuzz_targets.append(name)
    return fuzz_targets

def buildOSSFuzzers(project):
    global BUILD_CACHE_TIMEOUT

    try:
        os.chdir('oss-fuzz')
        # check build cache
        try:
            with open("../.build_cache_%s"%project, "r") as f:
                cache = f.read()
                if len(cache) == 0: cache = 0.0
        except:
            cache = None
        # if there is no build cache, or last build cache is invalid, then build.
        if cache == None or (float(cache) + BUILD_CACHE_TIMEOUT) < time.time():
            os.system('echo y | sudo python3 infra/helper.py build_image %s' % project)
            os.system('sudo python3 infra/helper.py build_fuzzers --sanitizer address %s' % project)
            # if there is existing corpus, reduce it into half.
            for c in '01234567':
                os.system('sudo rm build/out/%s/*_corpus/%s*' % (project, c))
        fuzz_targets = _get_fuzz_targets(project)
        for target in fuzz_targets:
            print("[%s] build OK" % target)
        # save build cache
        with open("../.build_cache_%s"%project, "w") as f:
            f.write(str(time.time()))
    finally:
        os.chdir('..')
        return fuzz_targets

def runOSSFuzzer(project, fuzzer, sec):
    try:
        # prepare corpus (skip if repeat)
        os.chdir('oss-fuzz')
        cmd = 'sudo mkdir build/out/%s/%s_corpus 2>/dev/null && ' % (project,fuzzer)
        cmd += 'sudo unzip build/out/%s/%s_seed_corpus.zip -d build/out/%s/%s_corpus' % (project,fuzzer,project,fuzzer)
        os.system(cmd)

        # run fuzzing session
        cmd = 'sudo python3 infra/helper.py run_fuzzer '
        cmd += '%s %s ' % (project, fuzzer)
        cmd += "'-max_total_time=%d " % (sec)
        cmd += '%s_corpus/ ' % (fuzzer)
        cmd += "</dev/null;echo testaaaaaaa > crash-123123123;pwd;ls -al; #'"
        os.system(cmd)

        # report to master
        crash_list = glob.glob("build/out/%s/crash-*" % project)
        params = {"botid":botid}
        params['crash_count'] = 0
        params['project'] = project
        params['fuzzer'] = fuzzer
        print(crash_list)
        if len(crash_list) > 0:
            params['crash_count'] = len(crash_list)
            i = 0
            for crash in crash_list:
                with open(crash, 'rb') as f:
                    buf = f.read()
                params['crash-%d'%i] = base64.b64encode(buf).decode('ascii')
        ret = requests.post(MASTER_URL+'/report', json=params)
        ret = ret.json()
        if ret['retcode'] != 0:
            print('\033[1;31m[WARN] Report Error: %s\033[0m' % ret['msg'])
        else:
            print('\033[1;32m[INFO] Report OK\033[0m')

    except Exception as ex:
        print(ex)
    finally:
        os.chdir('..')


if __name__ == "__main__":
    print("fuzzing-bot client version 1.0")
    try:
        botid = input('input your ID: ')
        botid = hashlib.md5(botid.encode()).hexdigest()
        if not auth(botid):
            os._exit(-1)
        if not sync_config(botid):
            raise 1
        print("SESSION_TIME: " + str(SESSION_TIME))
        print("BUILD_CACHE_TIMEOUT: " + str(BUILD_CACHE_TIMEOUT))
    except:
        print("\033[1;33m[WARN] Error in session setup. Using default config.\033[0m")
        print("\033[1;33m[WARN] If this problem repeats, please tell admin.\033[0m")
        print("SESSION_TIME (default): " + str(SESSION_TIME))
        print("BUILD_CACHE_TIMEOUT (default): " + str(BUILD_CACHE_TIMEOUT))

    # do everything.
    if len(sys.argv) == 1:
        getOSSFuzz()
        fuzz_targets = buildOSSFuzzers("c-ares")
        target = random.choice(fuzz_targets)
        print("Running [%s]..." % target)
        runOSSFuzzer("c-ares", target, SESSION_TIME)


