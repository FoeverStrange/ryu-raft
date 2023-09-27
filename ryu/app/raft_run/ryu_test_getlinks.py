from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, set_ev_cls
from ryu.topology import api

class PrintTopology(app_manager.RyuApp):

    def __init__(self, *args, **kwargs):
        super(PrintTopology, self).__init__(*args, **kwargs)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, MAIN_DISPATCHER)
    def switch_features_handler(self, ev):
        # 获取所有交换机
        switches = api.get_all_switch(self)
        
        # 获取所有连接（链路）
        links = api.get_all_link(self)

        print("Switches:")
        for switch in switches:
            print(switch)

        print("\nLinks:")
        for link in links:
            print(link)
