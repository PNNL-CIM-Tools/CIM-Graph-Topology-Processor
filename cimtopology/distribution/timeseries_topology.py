
def get_snapshot_topology(self, model_mrid, simulation_id, timestamp):
    self.log.info('Building snapshot topology for ' + str(model_mrid))
    # Topology = TopologyDictionary(self.gapps, model_mrid)
    # network = NetworkModel(self.gapps)
    # network.build_equip_dicts(model_mrid, Topology)
    # EqTypes = ['ACLineSegment', 'PowerTransformer', 'TransformerTank', 'SynchronousMachine']
    # Topology.build_linknet(EqTypes)
    
        #Query for switch position measurement mRIDs
    # request = {"modelId": model_mrid,
    #            "requestType": "QUERY_OBJECT_MEASUREMENTS",
    #            "resultFormat": "JSON",
    #            "objectType": "LoadBreakSwitch"
    #            }

    # response = self.gapps.get_response(t.REQUEST_POWERGRID_DATA,request,timeout=15)
    
    # equipment_dict = {}
    # measurement_dict = {}
    # meas_map={}

    # for measurement in response["data"]:
    #     if measurement["type"] == "Pos":
    #         measid = measurement["measid"]
    #         meas_map[measid] = {}
    #         meas_map[measid]['eqtype'] = measurement['eqtype']
    #         meas_map[measid]['eqid'] = measurement["eqid"]



    # # Query for switch measurments
    # message = {
    #     "queryMeasurement":"simulation",
    #     "queryFilter":{"simulation_id": str(simulation_id),
    #         "startTime": str(round(int(timestamp)-1)),
    #         "endTime": str(round(int(timestamp)+3)),
    #         "measurement_mrid": list(measurement_dict.keys())
    #                   },
    #         "responseFormat":"JSON" }


    # influx_response = self.gapps.get_response(t.TIMESERIES, message) # Pass API call
    # import time
    # counter=0
    # while not influx_response['data'] and counter <5:
    #     influx_response = self.gapps.get_response(t.TIMESERIES, message) # Pass API call
    #     self.log.info('Waiting 10 seconds for data to be written to Timeseries Database')
    #     time.sleep(10)
    #     counter=counter+1
    #     if counter==5: self.log.info("No Timeseries data found. Returning default topology")

    # # Parse timeseries data for current switch positions
    # for measurement in influx_response["data"]:
    #     measid = measurement["measurement_mrid"]
    #     time = measurement["time"]
    #     if measid in meas_map:
    #         eqid = meas_map[measid]['eqid']
    #         eqtype = meas_map[measid]['eqtype']
    #         Topology.EquipDict[eqtype][eqid]["open"] = measurement['value']
            
    # Topology.update_switches()
    # Topology.build_feeder_islands()
    
    # return Topology, time