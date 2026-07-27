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
 * \addtogroup sdn-schedule-advertisement
 * @{
 *
 * @file sdn-schedule-advertisement.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Schedule advertisements processing
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "net/sdn-net/sdn-schedule-advertisement.h"
#include "net/sdn-net/sd-wsn.h"
#include "net/sdn-net/sdn-neighbor-discovery.h"
#include "net/sdn-net/sdn-data-packets.h"
#include "net/sdn-net/sdn-advertisement.h"

#if BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED
#include "net/mac/tsch/tsch.h"
#include "services/orchestra-sdn-centralised/orchestra.h"
#endif /* BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED */

#if BUILD_WITH_SDN_ORCHESTRA
#include "net/mac/tsch/tsch.h"
#include "services/orchestra-sdn/orchestra.h"
#endif /* BUILD_WITH_SDN_ORCHESTRA */

/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "SA"
#if LOG_CONF_LEVEL_SA
#define LOG_LEVEL LOG_CONF_LEVEL_SA
#else
#define LOG_LEVEL LOG_LEVEL_NONE
#endif /* LOG_CONF_LEVEL_SA */

static uint16_t sequence_number = 0;

/*---------------------------------------------------------------------------*/
int sdn_sa_input(void)
{
    uint16_t seq = sdnip_htons(SDN_SA_BUF->seq);
    LOG_INFO("Received (SEQ:%u)\n", seq);
    // We first check whether we have seen this packet before.
    if (seq < sequence_number)
    {
        LOG_WARN("pkt already processed, dropping\n");
        return 0;
    }
#if BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED
    // Set the slotframe size
    uint8_t sf_len = SDN_SA_BUF->sf_len;
    if (sf_len != 0)
        NETSTACK_CONF_SDN_SLOTFRAME_SIZE_CALLBACK(sf_len, seq);
    // Process schedules
    uint8_t num_schedules, i, type, channel_offset, time_offset;
    linkaddr_t scr, dst;
    num_schedules = SDN_SA_BUF->payload_len / SDN_SAPL_LEN;
    for (i = 0; i < num_schedules; i++)
    {
        // Only process SA for us
        scr.u16 = sdnip_htons(SDN_SA_PAYLOAD(i)->scr.u16);
        if (linkaddr_cmp(&scr, &linkaddr_node_addr))
        {
            type = SDN_SA_PAYLOAD(i)->type;
            channel_offset = SDN_SA_PAYLOAD(i)->channel_offset;
            time_offset = SDN_SA_PAYLOAD(i)->time_offset;
            dst.u16 = sdnip_htons(SDN_SA_PAYLOAD(i)->dst.u16);
            // PRINTF("Type: %u, chan: %u, time: %u, scr: %d.%d, dst= %d.%d\n",
            //        type, channel_offset, time_offset, scr.u8[0], scr.u8[1], dst.u8[0], dst.u8[1]);
            NETSTACK_CONF_SDN_SA_LINK_CALLBACK(type, channel_offset, time_offset, &dst);
        }
    }
#endif /* BUILD_WITH_SDN_ORCHESTRA_CENTRALIZED */
    /* Look in the nbr TSCH queue with packets and update ts and ch */
    tsch_queue_reset();
    /* Reset the data packets sequence number */
#if !BUILD_WITH_SDN_CONTROLLER_SERIAL
    sdn_data_reset_seq(seq);
    sdn_na_reset_seq(seq);
#endif
    // Update sequence number received
    sequence_number = seq + 1;

    return 1;
}

/** @} */
/*---------------------------------------------------------------------------*/