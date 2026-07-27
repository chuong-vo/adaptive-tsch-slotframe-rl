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
 * \addtogroup sdn
 * @{
 *
 * @file sdn.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief sdn header
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#ifndef SDN_H_
#define SDN_H_

#include "contiki.h"
#include "net/linkaddr.h"

/* SDN controller address */
extern linkaddr_t ctrl_addr;

/**
 * The ICMP6 event.
 *
 * This event is posted to a process whenever a ND event has occurred.
 */
// extern process_event_t tcpip_icmp6_event;

/**
 * \brief register an ICMPv6 callback
 * \return 0 if success, 1 if failure (one application already registered)
 *
 * This function just registers a process to be polled when
 * an ICMPv6 message is received.
 * If no application registers, some ICMPv6 packets will be
 * processed by the "kernel" as usual (NS, NA, RS, RA, Echo request),
 * others will be dropped.
 * If an application registers here, it will be polled with a
 * process_post_synch every time an ICMPv6 packet is received.
 */
// uint8_t icmp6_new(void *appstate);

/**
 * This function is called at reception of an ICMPv6 packet
 * If an application registered as an ICMPv6 listener (with
 * icmp6_new), it will be called through a process_post_synch()
 */
// void tcpip_icmp6_call(uint8_t type);

/**
 * The uIP event.
 *
 * This event is posted to a process whenever a sdn event has occurred.
 */
extern process_event_t sdn_event;

/**
 * \brief      Deliver an incoming packet to the SDN stack
 *
 *             This function is called by network device drivers to
 *             deliver an incoming packet to the TCP/IP stack. The
 *             incoming packet must be present in the uip_buf buffer,
 *             and the length of the packet must be in the global
 *             uip_len variable.
 */
void sdn_ip_input(void);

#if BUILD_WITH_SDN_CONTROLLER_SERIAL
/**
 * \brief      Deliver an incoming packet to the serial interface
 *
 *             This function is called by network device drivers to
 *             deliver an incoming packet to serial interface. The
 *             incoming packet must be present in the uip_buf buffer,
 *             and the length of the packet must be in the global
 *             uip_len variable.
 */
void serial_ip_output(void);
#endif /* BUILD_WITH_SDN_CONTROLLER_SERIAL */

/**
 * \brief Output packet to layer 2
 * The eventual parameter is the MAC address of the destination.
 */
uint8_t sdn_ip_output(const linkaddr_t *dest);

/**
 * \brief This function does address resolution and then calls tcpip_output
 */
void sdn_output(void);

/**
 * \brief Is forwarding generally enabled?
 */
extern unsigned char sdn_do_forwarding;

/*
 * Are we at the moment forwarding the contents of uip_buf[]?
 */
extern unsigned char sdn_is_forwarding;

#define sdn_set_forwarding(forwarding) sdn_do_forwarding = (forwarding)

PROCESS_NAME(sdn_process);

#endif /* TCPIP_H_ */

/** @} */