from ryu.base import app_manager

from ryu.ofproto import ofproto_v1_3

from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER,CONFIG_DISPATCHER,DEAD_DISPATCHER #只是表示datapath数据路径的状态
from ryu.controller.handler import set_ev_cls

from ryu.lib import hub
from ryu.lib.packet import packet,ethernet

from ryu.topology import event,switches
from ryu.topology.api import get_switch,get_link,get_host

import threading,time,random

DELAY_MONITOR_PERIOD = 5

class TopoDetect(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self,*args,**kwargs):
        super(TopoDetect,self).__init__(*args,**kwargs)
        self.topology_api_app = self
        self.name = "topology"
        self.link_list = None
        self.switch_list = None
        self.host_list = None

        self.dpid2id = {}
        self.id2dpid = {}
        self.dpid2switch = {}

        self.ip2host = {}
        self.ip2switch = {}

        self.net_size = 0
        self.net_topo = []

        self.net_flag = False
        self.net_arrived = 0
        
        self.monitor_thread = hub.spawn(self._monitor)

    def _monitor(self):
        """
        协程实现伪并发，探测拓扑状态
        """
        while True:
            #print("------------------_monitor")
            self._host_add_handler(None) #主机单独提取处理
            self.get_topology(None)
            if self.net_flag:
                try:
                    self.show_topology()
                except Exception as err:
                    print("Please use cmd: pingall to detect topology and wait a moment")
            hub.sleep(DELAY_MONITOR_PERIOD) #5秒一次


    @set_ev_cls(ofp_event.EventOFPSwitchFeatures,CONFIG_DISPATCHER)
    def switch_feature_handle(self,ev):
        """
        datapath中有配置消息到达
        """
        #print("------XXXXXXXXXXX------%d------XXXXXXXXXXX------------switch_feature_handle"%self.net_arrived)
        #print("----%s----------",ev.msg)
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        match = ofp_parser.OFPMatch()

        actions = [ofp_parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,ofproto.OFPCML_NO_BUFFER)]

        self.add_flow(datapath=datapath,priority=0,match=match,actions=actions,extra_info="config infomation arrived!!")


    def add_flow(self,datapath,priority,match,actions,idle_timeout=0,hard_timeout=0,extra_info=None):
        #print("------------------add_flow:")
        if extra_info != None:
            print(extra_info)
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        inst = [ofp_parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,actions)]

        mod = ofp_parser.OFPFlowMod(datapath=datapath,priority=priority,
                                    idle_timeout=idle_timeout,
                                    hard_timeout=hard_timeout,
                                    match=match,instructions=inst)
        datapath.send_msg(mod);

    @set_ev_cls(ofp_event.EventOFPPacketIn,MAIN_DISPATCHER)
    def packet_in_handler(self,ev):
        #print("------------------packet_in_handler")
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        ofp_parser = datapath.ofproto_parser

        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        dst = eth_pkt.dst
        src = eth_pkt.src

        #self.logger.info("------------------Controller %s get packet, Mac address from: %s send to: %s , send from datapath: %s,in port is: %s"
        #                    ,dpid,src,dst,dpid,in_port)
        self.get_topology(None)


    @set_ev_cls([event.EventHostAdd])
    def _host_add_handler(self,ev):    #主机信息单独处理，不属于网络拓扑
        self.host_list = get_host(self.topology_api_app) #3.需要使用pingall,主机通过与边缘交换机连接，才能告诉控制器
        #获取主机信息字典ip2host{ipv4:host object}  ip2switch{ipv4:dpid}
        for i,host in enumerate(self.host_list):
            self.ip2switch["%s"%host.ipv4] = host.port.dpid
            self.ip2host["%s"%host.ipv4] = host


    events = [event.EventSwitchEnter, event.EventSwitchLeave,
               event.EventSwitchReconnected,
               event.EventPortAdd, event.EventPortDelete,
               event.EventPortModify,
               event.EventLinkAdd, event.EventLinkDelete]
    @set_ev_cls(events)
    def get_topology(self,ev):
        #print("------+++++++++++------%d------+++++++++++------------get_topology"%self.net_arrived)

        self.net_flag = False
        self.net_topo = []

        #print("-----------------get_topology")
        #获取所有的交换机、链路
        self.switch_list = get_switch(self.topology_api_app) #1.只要交换机与控制器联通，就可以获取
        self.link_list = get_link(self.topology_api_app) #2.在ryu启动时，加上--observe-links即可用于拓扑发现
        
        #获取交换机字典id2dpid{id:dpid} dpid2switch{dpid:switch object}
        for i,switch in enumerate(self.switch_list):
            self.id2dpid[i] = switch.dp.id
            self.dpid2id[switch.dp.id] = i
            self.dpid2switch[switch.dp.id] = switch


        #根据链路信息，开始获取拓扑信息
        self.net_size = len(self.id2dpid) #表示网络中交换机个数
        for i in range(self.net_size):
            self.net_topo.append([0]*self.net_size)

        for link in self.link_list:
            src_dpid = link.src.dpid
            src_port = link.src.port_no

            dst_dpid = link.dst.dpid
            dst_port = link.dst.port_no

            try:
                sid = self.dpid2id[src_dpid]
                did = self.dpid2id[dst_dpid]
            except KeyError as e:
                #print("--------------Error:get KeyError with link infomation(%s)"%e)
                return
            self.net_topo[sid][did] = [src_port,0] #注意：这里0表示存在链路，后面可以修改为时延
            self.net_topo[did][sid] = [dst_port,0] #注意：修改为列表，不要用元组，元组无法修改，我们后面要修改时延


        self.net_flag = True #表示网络拓扑创建成功

    def show_topology(self):
        print("-----------------show_topology")
        print("----------switch network----------")
        line_info = "         "
        for i in range(self.net_size):
            line_info+="        s%-5d        "%self.id2dpid[i]
        print(line_info)
        for i in range(self.net_size):
            line_info = "s%d      "%self.id2dpid[i]
            for j in range(self.net_size):
                if self.net_topo[i][j] == 0:
                    line_info+="%-22d"%0
                else:
                    line_info+="(%d,%.12f)    "%tuple(self.net_topo[i][j])
            print(line_info)

        print("----------host 2 switch----------")
        for key,val in self.ip2switch.items():
            print("%s---s%d"%(key,val))
