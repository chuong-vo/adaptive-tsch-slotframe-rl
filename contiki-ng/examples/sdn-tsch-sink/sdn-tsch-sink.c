/*
 * Copyright (c) 2022, Technical University of Denmark.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 *
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 * 3. Neither the name of the copyright holder nor the names of its
 *    contributors may be used to endorse or promote products derived
 *    from this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE
 * COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
 * STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
 * OF THE POSSIBILITY OF SUCH DAMAGE.
 *
 */

/**
 * @file sdn-controller-serial.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief SDN TSCH example
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "contiki.h"
#include "sdn-serial.h"
#include "sdn-serial-protocol.h"
#include "net/netstack.h"
#include "net/sdn-net/sd-wsn.h"
#include "net/sdn-net/sdn-net.h"
#include "net/mac/tsch/tsch.h"
#include "net/sdn-net/sdn.h"
#include "sys/node-id.h"
#include <string.h>
#include <stdio.h> /* For printf() */

#if CONTIKI_TARGET_IOTLAB
#include "platform.h"
#endif /* CONTIKI_TARGET_IOTLAB */

#if MAC_CONF_WITH_TSCH
#include "net/mac/tsch/tsch.h"
#endif

/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "App"
#define LOG_LEVEL LOG_LEVEL_INFO

linkaddr_t ctrl_addr;

/*---------------------------------------------------------------------------*/
PROCESS(sdn_tsch, "serial-sdn-controller example");
AUTOSTART_PROCESSES(&sdn_tsch);
/*-------------------------------Process thread------------------------------*/
PROCESS_THREAD(sdn_tsch, ev, data)
{
    int is_coordinator;

    PROCESS_BEGIN();

    // Set the controller address as 1.1 where the sink takes the 1.0 address
    ctrl_addr.u8[0] = 1;
    ctrl_addr.u8[1] = 1;

    is_coordinator = 0;

#if BUILD_WITH_SDN_CONTROLLER_SERIAL || SDN_CONTROLLER
    is_coordinator = 1;
#endif

    if (is_coordinator)
    {
        LOG_INFO("Setting as the root\n");
        tsch_set_coordinator(1);
    }

#if CONTIKI_TARGET_IOTLAB
    // Possible values for M3 radio 3, 2.8, 2.3, 1.8, 1.3, 0.7, 0.0, -1,
    // -2, -3, -4, -5, -7, -9, -12, -17
    // see phy.h for correct value to use
    NETSTACK_RADIO.set_value(RADIO_PARAM_TXPOWER, PHY_POWER_m30dBm);
#endif /* CONTIKI_TARGET_IOTLAB */

    NETSTACK_MAC.on();

    process_start(&sdn_process, NULL);

#if BUILD_WITH_SDN_CONTROLLER_SERIAL || SDN_CONTROLLER
    /* start the sdn serial interface */
    sdn_serial_protocol_init();
#endif

    while (1)
    {
        PROCESS_YIELD();
    }

    PROCESS_END();
}
/*---------------------------------------------------------------------------*/
