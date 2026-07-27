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
 * \addtogroup sdn-power-measurement
 * @{
 *
 * @file sdn-routing.c
 * @author F. Fernando Jurado-Lasso <ffjla@dtu.dk>
 * @brief Sensor nodes power measurement
 * @version 0.1
 * @date 2022-10-15
 *
 * @copyright Copyright (c) 2022, Technical University of Denmark.
 *
 */

#include "contiki.h"
#include "sys/energest.h"
#include "sdn-power-measurement.h"
#include <stdio.h>
#include <limits.h>
#include <inttypes.h>

/* Log configuration */
#include "sys/log.h"
#define LOG_MODULE "SDN-POWER"
#if LOG_CONF_LEVEL_SDN_POWER
#define LOG_LEVEL LOG_CONF_LEVEL_SDN_POWER
#else
#define LOG_LEVEL LOG_LEVEL_NONE
#endif /* LOG_CONF_LEVEL_SDN_POWER */

/* EWMA (exponential moving average) used to maintain statistics over time */
#define EWMA_SCALE 100
#define EWMA_ALPHA 40

static uint64_t last_tx, last_rx, last_time, last_cpu, last_lpm, last_deep_lpm;

uint64_t moving_avg_power;

PROCESS(sdn_power_measurement_process, "SDN power measurement module");

/*---------------------------------------------------------------------------*/
#if !CONTIKI_TARGET_IOTLAB
static uint64_t
to_permil(uint64_t delta_metric, uint64_t delta_time)
{
  return (1000ul * delta_metric) / delta_time;
}
#endif
/*---------------------------------------------------------------------------*/
#if !CONTIKI_TARGET_IOTLAB
static void
log_energest(const char *name, uint64_t delta, uint64_t delta_time)
{
  LOG_INFO("%-12s: %10" PRIu64 "/%10" PRIu64 " (%" PRIu64 " permil)\n",
           name, delta, delta_time, to_permil(delta, delta_time));
}
#endif
/*---------------------------------------------------------------------------*/
static uint64_t
calc_power(uint64_t cpu, uint64_t lpm, uint64_t dlpm, uint64_t transmit, uint64_t listen,
           uint64_t stime)
{
  return 1000 * SDN_POWER_MEASUREMENT_VOLTAGE *
         (cpu * SDN_POWER_MEASUREMENT_CPU +
          lpm * SDN_POWER_MEASUREMENT_LPM +
          dlpm * SDN_POWER_MEASUREMENT_DLPM +
          transmit * SDN_POWER_MEASUREMENT_TX +
          listen * SDN_POWER_MEASUREMENT_RX) /
         stime;
}
/*---------------------------------------------------------------------------*/
static void
simple_energest_step(void)
{
#if !CONTIKI_TARGET_IOTLAB
  static unsigned count = 0;
#endif
  uint64_t curr_tx, curr_rx, curr_time, curr_cpu, curr_lpm, curr_deep_lpm;
  uint64_t delta_time;
  uint64_t power;

  energest_flush();

  curr_time = ENERGEST_GET_TOTAL_TIME();
  curr_cpu = energest_type_time(ENERGEST_TYPE_CPU);
  curr_lpm = energest_type_time(ENERGEST_TYPE_LPM);
  curr_deep_lpm = energest_type_time(ENERGEST_TYPE_DEEP_LPM);
  curr_tx = energest_type_time(ENERGEST_TYPE_TRANSMIT);
  curr_rx = energest_type_time(ENERGEST_TYPE_LISTEN);

  delta_time = MAX(curr_time - last_time, 1);

  /* Calculate the sample average power consumption */
  power = calc_power(curr_cpu - last_cpu, curr_lpm - last_lpm,
                     curr_deep_lpm - last_deep_lpm, curr_tx - last_tx, curr_rx - last_rx, delta_time);

  /* Calculate the moving average */
  moving_avg_power = (moving_avg_power * (EWMA_SCALE - EWMA_ALPHA) +
                      power * EWMA_ALPHA) /
                     EWMA_SCALE;

#if !CONTIKI_TARGET_IOTLAB
  LOG_INFO("--- Period summary #%u (%" PRIu64 " seconds)\n",
           count++, delta_time / ENERGEST_SECOND);
  LOG_INFO("Total time  : %10" PRIu64 "\n", delta_time);
  log_energest("CPU", curr_cpu - last_cpu, delta_time);
  log_energest("LPM", curr_lpm - last_lpm, delta_time);
  log_energest("Deep LPM", curr_deep_lpm - last_deep_lpm, delta_time);
  log_energest("Radio Tx", curr_tx - last_tx, delta_time);
  log_energest("Radio Rx", curr_rx - last_rx, delta_time);
  log_energest("Radio total", curr_tx - last_tx + curr_rx - last_rx,
               delta_time);
  log_energest("Power (uW)", power, delta_time);
  log_energest("EMA (uW)", moving_avg_power, delta_time);
#endif

  last_time = curr_time;
  last_cpu = curr_cpu;
  last_lpm = curr_lpm;
  last_deep_lpm = curr_deep_lpm;
  last_tx = curr_tx;
  last_rx = curr_rx;
}
/*---------------------------------------------------------------------------*/
PROCESS_THREAD(sdn_power_measurement_process, ev, data)
{
  static struct etimer periodic_timer;
  PROCESS_BEGIN();

  moving_avg_power = SDN_POWER_MEASUREMENT_INIT_POWER;

  etimer_set(&periodic_timer, SDN_POWER_MEASUREMENT_PERIOD);

  while (1)
  {
    PROCESS_WAIT_EVENT_UNTIL(etimer_expired(&periodic_timer));
    etimer_reset(&periodic_timer);
    simple_energest_step();
  }
  PROCESS_END();
}

/*---------------------------------------------------------------------------*/
void sdn_power_measurement_init(void)
{
  energest_flush();
  last_time = ENERGEST_GET_TOTAL_TIME();
  last_cpu = energest_type_time(ENERGEST_TYPE_CPU);
  last_lpm = energest_type_time(ENERGEST_TYPE_LPM);
  last_deep_lpm = energest_type_time(ENERGEST_TYPE_DEEP_LPM);
  last_tx = energest_type_time(ENERGEST_TYPE_TRANSMIT);
  last_rx = energest_type_time(ENERGEST_TYPE_LISTEN);
  process_start(&sdn_power_measurement_process, NULL);
}

/** @} */