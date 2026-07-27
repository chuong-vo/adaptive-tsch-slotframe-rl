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
 * \addtogroup sdn-route-advertisement
 * @{
 *
 * @file sdn-route-advertisement.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Routes advertisements processing
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "net/sdn-net/sdn-route-advertisement.h"
#include "net/sdn-net/sd-wsn.h"
#include "net/sdn-net/sdn-neighbor-discovery.h"
#include "sdn-ds-route.h"

/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "RA"
#if LOG_CONF_LEVEL_RA
#define LOG_LEVEL LOG_CONF_LEVEL_RA
#else
#define LOG_LEVEL LOG_LEVEL_NONE
#endif /* LOG_CONF_LEVEL_RA */

static uint16_t sequence_number = 0;

/*---------------------------------------------------------------------------*/
int sdn_ra_input(void)
{
    uint16_t seq = sdnip_htons(SDN_RA_BUF->seq);
    LOG_INFO("Received (SEQ:%u)\n", seq);
    // We first check whether we have seen this packet before.
    if (seq < sequence_number)
    {
        LOG_WARN("pkt already processed, dropping\n");
        return 0;
    }
    // Update sequence number received
    sequence_number = seq + 1;
    // Process schedules
    uint8_t num_routes, i;
    linkaddr_t scr, dst, via;
    num_routes = SDN_RA_BUF->payload_len / SDN_RAPL_LEN;
    for (i = 0; i < num_routes; i++)
    {
        // Only process RA for us
        scr.u16 = sdnip_htons(SDN_RA_PAYLOAD(i)->scr.u16);
        if (linkaddr_cmp(&scr, &linkaddr_node_addr))
        {
            dst.u16 = sdnip_htons(SDN_RA_PAYLOAD(i)->dest.u16);
            via.u16 = sdnip_htons(SDN_RA_PAYLOAD(i)->via.u16);
            // PRINTF("scr: %d.%d, dst: %d.%d, via: %d.%d\n",
            //        scr.u8[0], scr.u8[1], dst.u8[0], dst.u8[1], via.u8[0], via.u8[1]);
            sdn_ds_route_add(&dst, 0, &via, CONTROLLER);
        }
    }
    return 1;
}

/** @} */
/*---------------------------------------------------------------------------*/
