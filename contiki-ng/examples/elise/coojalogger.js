/* A simple log file generator script */

// TIMEOUT(144000000); /* 3600 seconds or 1 hour */
TIMEOUT(3600000000); /* 3600 seconds or 1 hour */

log.log("Starting COOJA logger\n");

timeout_function = function () {
    log.log("Script timed out.\n");
    log.testOK();
}

while (true) {
    if (msg) {
        log.log(time + " " + id + " " + msg + "\n");
    }

    YIELD();
}
