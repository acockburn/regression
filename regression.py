import argparse
import sys
import yaml
from subprocess import Popen, PIPE, STDOUT
import os.path
import difflib
import re
from threading import Thread
from time import sleep
import signal


def log(level, message):
    print(level, message)


def do_substitutions(line, global_subs, test_subs):
    if global_subs is not None:
        for i in global_subs:
            line = re.sub(i["search"], i["replace"], line)

    if test_subs is not None:
        for i in test_subs:
            line = re.sub(i["search"], i["replace"], line)

    return line


def check_against_baseline(baseline, output, global_subs, test_subs):
    with open(baseline) as fd:
        lines = []
        for line in fd:
            subline = do_substitutions(line, global_subs, test_subs)
            lines.append(subline)

    log("INFO", "Baseline Comparison:")
    diff = difflib.ndiff(lines, output)
    _pass = True
    for line in diff:
        log("INFO", line.rstrip("\n"))
        if line[0] != " ":
            _pass = False

    return _pass


def send_signal(p, sigtype, delay):
    sleep(delay)
    log("INFO", "Sending {}".format(sigtype))
    p.send_signal(signal.Signals[sigtype].value)


def run_test(test_dir, results_dir, test, baseline, global_subs):

    parameters = test["command"].split(" ")
    params = [p.replace("#", " ") for p in parameters]

    log("INFO", "-----------------------------------------------------")
    log("INFO", "Running test: '{}'".format(test["name"]))
    log("INFO", "-----------------------------------------------------")
    log("INFO", "Test Dir: {}".format(test_dir))
    log("INFO", "Results Dir: {}".format(results_dir))
    log("INFO", "Command: {}".format(params))
    log("INFO", "Run Dir: {}".format(test["run_dir"]))
    log("INFO", "Baseline: {}".format(test["baseline"]))

    p = Popen(params, cwd=test["run_dir"] ,stdout=PIPE, stderr=STDOUT)

    output = []

    thread = None
    if "signal" in test:
        thread = Thread(target=send_signal, args=(p, test["signal"]["type"], test["signal"]["delay"],))
        thread.start()

    while True:
        line = p.stdout.readline().decode("utf-8")
        if not line:
            break
        subline = do_substitutions(line, global_subs, test.get("subs"))
        log("INFO", subline.rstrip('\n'))
        output.append(subline)

    if "signal" in test:
        thread.join()

    if os.path.isfile(test["baseline"]) and not baseline:
        result = check_against_baseline(test["baseline"], output, global_subs, test.get("subs"))
    else:
        log("INFO", "Creating baseline")
        fd = open(test["baseline"], 'w')
        fd.writelines(output)
        result = True

    return result


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("-c", "--config", help="full path to config file", type=str, default=None)
    parser.add_argument("-b", "--baseline", help="specify a test to re-baseline", type=str, default=None,
                        action="append")
    parser.add_argument("-t", "--test", help="specify a specific test to run", type=str, default=None,
                        action="append")

    args = parser.parse_args()

    if args.config is None:
        log("ERROR", "Must supply a config file")
        sys.exit()

    try:

        with open(args.config, 'r') as yamlfd:
            config_file_contents = yamlfd.read()

        config = yaml.load(config_file_contents)

    except yaml.YAMLError as exc:
        print("ERROR", "Error loading configuration")
        if hasattr(exc, 'problem_mark'):
            if exc.context is not None:
                print("ERROR", "parser says")
                print("ERROR", str(exc.problem_mark))
                print("ERROR", str(exc.problem) + " " + str(exc.context))
            else:
                print("ERROR", "parser says")
                print("ERROR", str(exc.problem_mark))
                print("ERROR", str(exc.problem))
        sys.exit()

    # print(config)
    result = None
    report = {}
    failed = 0
    for test in config["tests"]:
        name = test["name"]
        if (args.test is None) or (args.test is not None and name in args.test):
            if args.baseline is not None and name in args.baseline:
                baseline = True
            else:
                baseline = False

            result = run_test(config["test_dir"], config["results_dir"], test, baseline, config.get("subs"))

            if result is True:
                log("INFO", "Test Passed")
                report[name] = True
            elif result is False:
                log("INFO", "Test Failed")
                report[name] = False
                failed += 1

    log("INFO", "-----------------------------------------------------")
    log("INFO", "Test Summary:")
    log("INFO", "-----------------------------------------------------")

    for result in report:
        if report[result] is True:
            status = "Passed"
        else:
            status = "Failed"
        log("INFO", "Test: {:<20}Result: {}".format(result, status))

    log("INFO", "-----------------------------------------------------")

    if failed == 0:
        log("INFO", "All tests passed")
    else:
        log("INFO", "Failed tests: {}".format(failed))

    log("INFO", "-----------------------------------------------------")

    if result is None:
        log("WARNING", "No test executed")
if __name__ == "__main__":
    main()
