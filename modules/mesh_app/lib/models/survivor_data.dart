/// ============================================================================
/// ResQnet Mesh - Survivor Data Model
/// ============================================================================
/// Represents a single survivor entry in the mesh relay table.
/// Each entry tracks who was detected, by whom, where, and signal strength.
/// ============================================================================

class SurvivorData {
  /// Unique 8-character beacon ID of the survivor
  final String survivorId;

  /// RSSI value when last detected (negative dBm, closer to 0 = stronger)
  int rssi;

  /// Latitude of the relay node that detected this survivor
  double relayLat;

  /// Longitude of the relay node that detected this survivor
  double relayLng;

  /// Device ID of the relay node that detected/forwarded this entry
  String relayNodeId;

  /// Hop count - how many relays this data has passed through
  int hopCount;

  /// Timestamp of the last update (UTC milliseconds)
  int lastSeenMs;

  SurvivorData({
    required this.survivorId,
    required this.rssi,
    required this.relayLat,
    required this.relayLng,
    required this.relayNodeId,
    this.hopCount = 0,
    int? lastSeenMs,
  }) : lastSeenMs = lastSeenMs ?? DateTime.now().millisecondsSinceEpoch;

  /// Age of this entry in human-readable format
  String get age {
    final diff = DateTime.now().millisecondsSinceEpoch - lastSeenMs;
    if (diff < 60000) return '${(diff / 1000).round()}s ago';
    if (diff < 3600000) return '${(diff / 60000).round()}m ago';
    return '${(diff / 3600000).round()}h ago';
  }

  /// Signal strength label
  String get signalLabel {
    if (rssi > -50) return 'STRONG';
    if (rssi > -70) return 'MEDIUM';
    return 'WEAK';
  }

  /// Convert to JSON for API sync
  Map<String, dynamic> toJson() => {
        'survivor_id': survivorId,
        'rssi': rssi,
        'relay_lat': relayLat,
        'relay_lng': relayLng,
        'relay_node_id': relayNodeId,
        'hop_count': hopCount,
        'last_seen_ms': lastSeenMs,
      };

  /// Parse from JSON (e.g., from BLE broadcast payload)
  factory SurvivorData.fromJson(Map<String, dynamic> json) => SurvivorData(
        survivorId: json['survivor_id'] as String,
        rssi: json['rssi'] as int,
        relayLat: (json['relay_lat'] as num).toDouble(),
        relayLng: (json['relay_lng'] as num).toDouble(),
        relayNodeId: json['relay_node_id'] as String,
        hopCount: json['hop_count'] as int? ?? 0,
        lastSeenMs: json['last_seen_ms'] as int?,
      );

  /// Encode essential fields into a compact BLE broadcast string
  /// Format: "SURV_ID|RSSI|LAT|LNG|RELAY_ID|HOPS"
  String toBlePayload() =>
      '$survivorId|$rssi|${relayLat.toStringAsFixed(6)}|${relayLng.toStringAsFixed(6)}|$relayNodeId|$hopCount';

  /// Decode from BLE broadcast payload string
  static SurvivorData? fromBlePayload(String payload) {
    try {
      final parts = payload.split('|');
      if (parts.length < 6) return null;
      return SurvivorData(
        survivorId: parts[0],
        rssi: int.parse(parts[1]),
        relayLat: double.parse(parts[2]),
        relayLng: double.parse(parts[3]),
        relayNodeId: parts[4],
        hopCount: int.parse(parts[5]),
      );
    } catch (_) {
      return null;
    }
  }
}
