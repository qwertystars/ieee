/// ============================================================================
/// ResQnet Mesh - Core Nearby Connections Service (Android)
/// ============================================================================
/// Handles:
///   - Nearby Connections advertising (Survivor + Relay)
///   - Nearby Connections discovery (Rescue)
///   - Gossip relay of mesh table entries
///   - Mesh table management
/// ============================================================================

import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'package:nearby_connections/nearby_connections.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart' as uuid_pkg;

import '../models/survivor_data.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// Enums
// ═══════════════════════════════════════════════════════════════════════════════

enum MeshMode { idle, survivor, rescue }

enum MeshStatus { inactive, scanning, advertising, relaying }

// ═══════════════════════════════════════════════════════════════════════════════
// MeshService - Nearby Connections Controller
// ═══════════════════════════════════════════════════════════════════════════════

class MeshService extends ChangeNotifier {
  // ── Nearby Core ───────────────────────────────────────────────────────────
  final Nearby _nearby = Nearby();
  static const Strategy _strategy = Strategy.P2P_CLUSTER;
  static const String _serviceId = 'com.resqnet.mesh';

  // ── State ─────────────────────────────────────────────────────────────────
  MeshMode _mode = MeshMode.idle;
  MeshStatus _status = MeshStatus.inactive;
  String _deviceId = '';
  double _lat = 0.0;
  double _lng = 0.0;
  bool _isRelaying = false;

  // ── Mesh Relay Table ──────────────────────────────────────────────────────
  final Map<String, SurvivorData> _meshTable = {};

  // ── Connections ───────────────────────────────────────────────────────────
  final Set<String> _connectedEndpoints = {};

  // ── Getters ───────────────────────────────────────────────────────────────
  MeshMode get mode => _mode;
  MeshStatus get status => _status;
  String get deviceId => _deviceId;
  bool get isRelaying => _isRelaying;
  double get lat => _lat;
  double get lng => _lng;
  List<SurvivorData> get meshTable => _meshTable.values.toList()
    ..sort((a, b) => b.lastSeenMs.compareTo(a.lastSeenMs));
  int get survivorCount => _meshTable.length;

  // ═════════════════════════════════════════════════════════════════════════
  // Initialization
  // ═════════════════════════════════════════════════════════════════════════

  /// Initialize the mesh service: generate/load device ID, get location
  Future<void> initialize() async {
    await _loadOrGenerateDeviceId();
    await _updateLocation();
    notifyListeners();
  }

  /// Generate a unique 8-char device ID or load from storage
  Future<void> _loadOrGenerateDeviceId() async {
    final prefs = await SharedPreferences.getInstance();
    _deviceId = prefs.getString('resqnet_device_id') ?? '';

    if (_deviceId.isEmpty) {
      const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
      final rng = Random.secure();
      _deviceId = List.generate(8, (_) => chars[rng.nextInt(chars.length)]).join();
      await prefs.setString('resqnet_device_id', _deviceId);
    }
  }

  /// Capture current GPS coordinates
  Future<void> _updateLocation() async {
    try {
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 10),
        ),
      );
      _lat = pos.latitude;
      _lng = pos.longitude;
    } catch (_) {
      debugPrint('[MeshService] Location unavailable, using last known.');
    }
  }

  /// Refresh GPS coordinates for sync
  Future<void> refreshLocation() async {
    await _updateLocation();
    notifyListeners();
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Mode Switching
  // ═════════════════════════════════════════════════════════════════════════

  /// Switch to Survivor Mode — advertise this device's beacon ID
  Future<void> startSurvivorMode() async {
    await stopAll();
    _mode = MeshMode.survivor;
    _status = MeshStatus.advertising;
    _isRelaying = true;
    notifyListeners();

    await _startAdvertising(isSurvivor: true);
  }

  /// Switch to Rescue/Relay Mode — discover survivors and relay data
  Future<void> startRescueMode() async {
    await stopAll();
    _mode = MeshMode.rescue;
    _status = MeshStatus.scanning;
    _isRelaying = true;
    await _updateLocation();
    notifyListeners();

    await _startAdvertising(isSurvivor: false);
    await _startDiscovery();
  }

  /// Stop all Nearby activity
  Future<void> stopAll() async {
    try {
      await _nearby.stopDiscovery();
    } catch (_) {}
    try {
      await _nearby.stopAdvertising();
    } catch (_) {}
    try {
      await _nearby.stopAllEndpoints();
    } catch (_) {}

    _connectedEndpoints.clear();
    _mode = MeshMode.idle;
    _status = MeshStatus.inactive;
    _isRelaying = false;
    notifyListeners();
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Nearby Connections — Advertising / Discovery
  // ═════════════════════════════════════════════════════════════════════════

  Future<void> _startAdvertising({required bool isSurvivor}) async {
    final name = isSurvivor ? 'RQ_$_deviceId' : 'RM_$_deviceId';

    await _nearby.startAdvertising(
      name,
      _strategy,
      serviceId: _serviceId,
      onConnectionInitiated: _onConnectionInitiated,
      onConnectionResult: _onConnectionResult,
      onDisconnected: _onDisconnected,
    );
  }

  Future<void> _startDiscovery() async {
    await _nearby.startDiscovery(
      'RC_$_deviceId',
      _strategy,
      serviceId: _serviceId,
      onEndpointFound: _onEndpointFound,
      onEndpointLost: _onEndpointLost,
    );
  }

  void _onEndpointFound(String endpointId, String endpointName, String serviceId) {
    if (_connectedEndpoints.contains(endpointId)) return;

    _nearby.requestConnection(
      _deviceId,
      endpointId,
      onConnectionInitiated: _onConnectionInitiated,
      onConnectionResult: _onConnectionResult,
      onDisconnected: _onDisconnected,
    );
  }

  void _onEndpointLost(String? endpointId) {
    if (endpointId == null) return;
    _connectedEndpoints.remove(endpointId);
    _updateRelayState();
  }

  void _onConnectionInitiated(String endpointId, ConnectionInfo info) {
    _nearby.acceptConnection(
      endpointId,
      onPayLoadRecieved: _onPayloadReceived,
      onPayloadTransferUpdate: _onPayloadTransferUpdate,
    );
  }

  void _onConnectionResult(String endpointId, Status status) {
    if (status == Status.CONNECTED) {
      _connectedEndpoints.add(endpointId);

      if (_mode == MeshMode.survivor) {
        _sendSurvivorBeacon(endpointId);
      } else if (_mode == MeshMode.rescue) {
        _sendGossip(endpointId);
      }
    } else {
      _connectedEndpoints.remove(endpointId);
    }

    _updateRelayState();
  }

  void _onDisconnected(String endpointId) {
    _connectedEndpoints.remove(endpointId);
    _updateRelayState();
  }

  void _updateRelayState() {
    if (_mode == MeshMode.idle) {
      _status = MeshStatus.inactive;
      _isRelaying = false;
    } else {
      _status = _mode == MeshMode.survivor ? MeshStatus.advertising : MeshStatus.scanning;
      _isRelaying = true;
    }
    notifyListeners();
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Payload Handling
  // ═════════════════════════════════════════════════════════════════════════

  void _onPayloadReceived(String endpointId, Payload payload) {
    if (payload.type != PayloadType.BYTES || payload.bytes == null) return;

    final message = utf8.decode(payload.bytes!);

    if (message.startsWith('SURV|')) {
      _handleSurvivorPing(message);
      _broadcastGossip(exceptEndpoint: endpointId);
      return;
    }

    if (message.startsWith('RM_')) {
      final relayed = SurvivorData.fromBlePayload(message.substring(3));
      if (relayed != null) {
        relayed.hopCount += 1;
        _upsertSurvivor(relayed);
        _broadcastGossip(exceptEndpoint: endpointId);
      }
    }
  }

  void _onPayloadTransferUpdate(String endpointId, PayloadTransferUpdate update) {
    if (update.status == PayloadStatus.SUCCESS) {
      debugPrint('[Nearby] Payload delivered to $endpointId');
    }
  }

  void _handleSurvivorPing(String message) {
    final parts = message.split('|');
    if (parts.length < 2) return;
    final survivorId = parts[1];

    // Update location on each detection (best-effort)
    unawaited(_updateLocation());

    _upsertSurvivor(
      SurvivorData(
        survivorId: survivorId,
        rssi: -55,
        relayLat: _lat,
        relayLng: _lng,
        relayNodeId: _deviceId,
        hopCount: 0,
      ),
    );
  }

  Future<void> _sendSurvivorBeacon(String endpointId) async {
    final payload = 'SURV|$_deviceId';
    await _sendPayload(endpointId, payload);
  }

  Future<void> _sendGossip(String endpointId) async {
    for (final payload in getGossipPayloads()) {
      await _sendPayload(endpointId, payload);
    }
  }

  void _broadcastGossip({String? exceptEndpoint}) {
    for (final endpointId in _connectedEndpoints) {
      if (endpointId == exceptEndpoint) continue;
      _sendGossip(endpointId);
    }
  }

  Future<void> _sendPayload(String endpointId, String payload) async {
    final bytes = Uint8List.fromList(utf8.encode(payload));
    await _nearby.sendBytesPayload(endpointId, bytes);
  }

  // ═════════════════════════════════════════════════════════════════════════
  // Mesh Table Management
  // ═════════════════════════════════════════════════════════════════════════

  void _upsertSurvivor(SurvivorData incoming) {
    final existing = _meshTable[incoming.survivorId];

    if (existing == null) {
      _meshTable[incoming.survivorId] = incoming;
      debugPrint('[Mesh] NEW survivor detected: ${incoming.survivorId}');
    } else {
      final isNewer = incoming.lastSeenMs > existing.lastSeenMs;
      final isStronger = incoming.rssi > existing.rssi;
      final isFewerHops = incoming.hopCount < existing.hopCount;

      if (isNewer || isStronger || isFewerHops) {
        _meshTable[incoming.survivorId] = incoming;
        debugPrint('[Mesh] UPDATED survivor: ${incoming.survivorId}');
      }
    }

    notifyListeners();
  }

  void clearMeshTable() {
    _meshTable.clear();
    notifyListeners();
  }

  List<String> getGossipPayloads() {
    return _meshTable.values.map((s) => 'RM_${s.toBlePayload()}').toList();
  }

  Future<void> persistMeshTable() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonList = _meshTable.values.map((s) => s.toJson()).toList();
    await prefs.setString('resqnet_mesh_table', jsonEncode(jsonList));
    debugPrint('[Mesh] Persisted ${jsonList.length} entries to local storage.');
  }

  Future<void> restoreMeshTable() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('resqnet_mesh_table');
    if (raw != null) {
      try {
        final list = jsonDecode(raw) as List<dynamic>;
        for (final item in list) {
          final s = SurvivorData.fromJson(item as Map<String, dynamic>);
          _meshTable[s.survivorId] = s;
        }
        debugPrint('[Mesh] Restored ${_meshTable.length} entries from storage.');
        notifyListeners();
      } catch (e) {
        debugPrint('[Mesh] Failed to restore mesh table: $e');
      }
    }
  }

  @override
  void dispose() {
    stopAll();
    super.dispose();
  }
}
