from cimgraph.databases import GridappsdConnection

def get_base_topology(gapps: GridappsdConnection, model_mrid):
    gapps.log.info('Building base topology for ' + str(model_mrid))
    # Topology = TopologyDictionary(self.gapps, model_mrid)
    # network = NetworkModel(self.gapps)
    # network.build_equip_dicts(model_mrid, Topology)
    # EqTypes = ['ACLineSegment', 'PowerTransformer', 'TransformerTank', 'SynchronousMachine', 'PowerElectronicsConnection']
    # Topology.build_linknet(EqTypes)
    # Topology.update_switches()
    # Topology.build_feeder_islands()
    # return Topology   