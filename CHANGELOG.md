# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.1a0] - 2025-02-24

### Added
- Initial alpha release
- Hierarchical topology processing for T+D power systems
- GridAPPS-D service integration via topology_background_service.py
- Support for Distribution, Feeder, Switch, and Secondary Areas
- Equipment categorization (addressable/unaddressable)
- Measurement and boundary terminal identification
- CIM-Graph library integration (v0.4.3a0+)
- Support for multiple CIM data profiles (cimhub_2023, cimhub_ufls, cim18gmdm.canonical)

### Known Issues
- GET_BASE_TOPOLOGY request type not yet implemented
- GET_SNAPSHOT_TOPOLOGY request type not yet implemented
- Incomplete get_context_from_feeder_area() function in distributed_topo_message.py

[Unreleased]: https://github.com/PNNL-CIM-Tools/CIM-Graph-Topology-Processor/compare/v0.0.1a0...HEAD
[0.0.1a0]: https://github.com/PNNL-CIM-Tools/CIM-Graph-Topology-Processor/releases/tag/v0.0.1a0
