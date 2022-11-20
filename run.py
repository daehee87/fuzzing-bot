#!/usr/bin/python3
import sys, os, subprocess
import random, time, requests
import hashlib

# default configurations
SESSION_TIME = 3600
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
    print("oss-fuzz repo ready")

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
        os.chdir('oss-fuzz')
        cmd = 'sudo python3 infra/helper.py run_fuzzer '
        cmd += '%s %s ' % (project, fuzzer)
        cmd += "'-max_total_time=%d " % (sec)
        os.system('sudo mkdir build/out/%s/%s_corpus 2>/dev/null' % (project,fuzzer))
        cmd += '%s_corpus/ ' % (fuzzer)
        cmd += "</dev/null;echo CUSTOM-INFO;pwd;ls -al; #'"
        print(cmd)
        os.system(cmd)
    finally:
        os.chdir('..')


try:
    botid = input('Input ID: ')
    botid = hashlib.md5(botid.encode()).hexdigest()
    if not auth(botid):
        os._exit(-1)
except:
    print("[WARN] Error in session setup. Using default config.")
    print("[WARN] If this problem repeats, please tell admin.")

# do everything.
#if len(sys.argv) == 1:
#    getOSSFuzz()
#    fuzz_targets = buildOSSFuzzers("c-ares")
#    target = random.choice(fuzz_targets)
#    print("Running [%s]..." % target)
#    runOSSFuzzer("c-ares", target, 5)















