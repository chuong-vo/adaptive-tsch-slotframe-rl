CONTIKI_PROJECT = sdn-tsch-sink
all: $(CONTIKI_PROJECT)

CONTIKI = ../../

CFLAGS += -DPROJECT_CONF_H=\"project-conf.h\"

# Default SDN centralized scheduling
MAKE_WITH_SDN_ORCHESTRA ?= 1

# Default SDN node
WITH_SERIAL_SDN_CONTROLLER ?= 1

ifdef NODE_ID
CFLAGS += -DNODE_ID=$(NODE_ID)
endif

include $(CONTIKI)/Makefile.dir-variables


ifeq ($(MAKE_WITH_SDN_ORCHESTRA),1)
MODULES += $(CONTIKI_NG_SERVICES_DIR)/orchestra-sdn-centralised
MODULES += $(CONTIKI_NG_SERVICES_DIR)/sdn-power-measurement
else
MODULES += $(CONTIKI_NG_SERVICES_DIR)/orchestra-sdn
MODULES += $(CONTIKI_NG_SERVICES_DIR)/sdn-power-measurement
endif

ifeq ($(WITH_SERIAL_SDN_CONTROLLER),1)
MODULES += $(CONTIKI_NG_SERVICES_DIR)/sdn-controller-serial
endif

#use this to enable TSCH: MAKE_MAC = MAKE_MAC_TSCH
MAKE_MAC = MAKE_MAC_TSCH
MAKE_NET = MAKE_NET_SDN
MAKE_ROUTING = MAKE_ROUTING_SDN
include $(CONTIKI)/Makefile.include











