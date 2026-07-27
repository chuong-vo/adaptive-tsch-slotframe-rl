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
 * \addtogroup sdn-serial
 * @{
 *
 * @file sdn-serial.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief SDN serial interface
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "sdn-serial.h"
#include "sdn-serial-protocol.h"
#include <string.h> /* for memcpy() */

#include "lib/ringbuf.h"

/* Log configuration */
#define DEBUG 0
#if DEBUG
#include <stdio.h>
#include "net/sdn-net/sd-wsn.h"
#define PRINTF(...) printf(__VA_ARGS__)
#else
#define PRINTF(...)
#endif

#if (SDN_SERIAL_BUFSIZE & (SDN_SERIAL_BUFSIZE - 1)) != 0
#error SERIAL_LINE_CONF_BUFSIZE must be a power of two (i.e., 1, 2, 4, 8, 16, 32, 64, ...).
#error Change SERIAL_LINE_CONF_BUFSIZE in contiki-conf.h.
#endif

uint16_t sdn_serial_len;

static uint8_t rxbuf_data[SDN_SERIAL_BUFSIZE];
// static uint8_t txbuf_data[SDN_SERIAL_BUFSIZE];
static struct ringbuf rxbuf;

sdn_serial_send_char sdn_send_serial_function = NULL;

PROCESS(sdn_serial_process, "SDN serial driver");

process_event_t sdn_serial_ev;
/*---------------------------------------------------------------------------*/
/* Function to send a byte through Serial*/
static void sdn_serial_putchar(char data)
{
    if (sdn_send_serial_function)
    {
        (*sdn_send_serial_function)((int)data);
    }
}
/*---------------------------------------------------------------------------*/
int sdn_serial_send(void)
{
    // Packet size
    uint16_t size = sdn_serial_len;
    // uint8_t data = 0;
    // PRINTF("size to send %d\n", size);

    uint8_t *data;
    data = (uint8_t *)SDN_SERIAL_PACKET_BUF;

    sdn_serial_putchar((uint8_t)FRAME_BOUNDARY_OCTET);

    while (size)
    {
        if ((*data == CONTROL_ESCAPE_OCTET) || (*data == FRAME_BOUNDARY_OCTET))
        {
            sdn_serial_putchar((uint8_t)CONTROL_ESCAPE_OCTET);
            *data ^= INVERT_OCTET;
        }
        // PRINTF("in tx buffer %x\n", data);
        sdn_serial_putchar((uint8_t)*data);
        size--;
        data++;
    }
    sdn_serial_putchar((uint8_t)FRAME_BOUNDARY_OCTET);

    return 0;
}
/*---------------------------------------------------------------------------*/
int sdn_serial_input_byte(unsigned char c)
{
    static uint8_t overflow = 0; /* Buffer overflow: ignore until END */

    if (!overflow)
    {
        /* Add character */
        if (ringbuf_put(&rxbuf, c) == 0)
        {
            /* Buffer overflow: ignore the rest of the line */
            overflow = 1;
        }
    }
    else
    {
        /* Buffer overflowed:
         * Only (try to) add terminator characters, otherwise skip */
        if ((c == FRAME_BOUNDARY_OCTET) && ringbuf_put(&rxbuf, c) != 0)
        {
            overflow = 0;
        }
    }

    /* Wake up consumer process */
    process_poll(&sdn_serial_process);
    return 1;
}
/*---------------------------------------------------------------------------*/
PROCESS_THREAD(sdn_serial_process, ev, data)
{

    static char buf[SDN_SERIAL_BUFSIZE];
    static int ptr;
    static uint8_t overflow = 0; /* Buffer overflow: ignore until END */
    static uint8_t escape_character = 0;
    PROCESS_BEGIN();

    sdn_serial_ev = process_alloc_event();

    ptr = 0;

    while (1)
    {
        /* Fill application buffer until newline or empty */
        int c = ringbuf_get(&rxbuf);

        if (c == -1)
        {
            /* Buffer empty, wait for poll */
            PROCESS_YIELD();
        }
        else
        {
            if ((c != FRAME_BOUNDARY_OCTET))
            {
                if (escape_character)
                {
                    escape_character = 0;
                    c ^= INVERT_OCTET;
                }
                else if (c == CONTROL_ESCAPE_OCTET)
                {
                    escape_character = 1;
                    goto exit;
                }

                if (ptr < (SDN_SERIAL_MAX_PACKET_SIZE + 2))
                { // Adding 2 bytes from serial communication
                    buf[ptr++] = (uint8_t)c;
                    goto exit;
                }
                else
                {
                    overflow = 1;
                    PRINTF("Packet size overflow: %u bytes\n", ptr);
                    goto exit;
                }
            }
            else
            {
                if (escape_character == 1)
                {
                    PRINTF("serial: escape_character == true\n");
                    escape_character = 0;
                }
                else if (overflow)
                { /* We lost consistence, begin again */
                    /* Clear Buffer */
                    PRINTF("serial overflow\n");
                    overflow = 0;
                    ptr = 0;
                } /* If a valid frame is detected> FRAME_BOUNDARY + PACKET MINIMUM SIZE (HEADER), otherwise discard. */
                else if (ptr >= SDN_SERIAL_PACKETH_LEN)
                {
                    /* Wake up consumer process */
                    process_post(&sdn_serial_protocol_process, SERIAL_PACKET_INPUT, buf);
                    /* Wait until all processes have handled the serial line event */
                    if (PROCESS_ERR_OK ==
                        process_post(PROCESS_CURRENT(), PROCESS_EVENT_CONTINUE, NULL))
                    {
                        PROCESS_WAIT_EVENT_UNTIL(ev == PROCESS_EVENT_CONTINUE);
                    }
                    ptr = 0;
                }
                else
                {
                    /* re-synchronization. Start over*/
                    PRINTF("serial re-synchronization\n");
                    ptr = 0;
                }
            }
        exit:
            continue;
        }
    }

    PROCESS_END();
}
/*---------------------------------------------------------------------------*/
void sdn_serial_init(sdn_serial_send_char callback)
{
    ringbuf_init(&rxbuf, rxbuf_data, sizeof(rxbuf_data));
    sdn_send_serial_function = callback;
    PRINTF("Initialising sdn-serial.\n");
    process_start(&sdn_serial_process, NULL);
}
/*---------------------------------------------------------------------------*/
uint8_t sdn_serial_get_len(struct sdn_serial_packet_hdr *hdr)
{
    return hdr->payload_len + SDN_SERIAL_PACKETH_LEN;
}

/** @} */
/*---------------------------------------------------------------------------*/