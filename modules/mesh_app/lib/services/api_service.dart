/// ============================================================================
/// ResQnet Mesh - API Sync Service
/// ============================================================================
/// Handles POSTing the mesh relay table to the FastAPI Command Center backend
/// when connectivity is restored.
/// ============================================================================

import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/survivor_data.dart';

class ApiService {
  /// Command Center backend URL (local network or when internet is restored)
  static const String _defaultBaseUrl = 'http://172.45.1.133:8000';

  final String baseUrl;

  ApiService({String? baseUrl}) : baseUrl = baseUrl ?? _defaultBaseUrl;

  /// POST the entire mesh table to the Command Center
  /// Returns true if sync was successful
  Future<SyncResult> syncMeshTable({
    required List<SurvivorData> meshTable,
    required String deviceId,
    required double deviceLat,
    required double deviceLng,
  }) async {
    final endpoint = '$baseUrl/api/mesh/sync';

    final payload = {
      'device_id': deviceId,
      'device_lat': deviceLat,
      'device_lng': deviceLng,
      'timestamp': DateTime.now().toUtc().toIso8601String(),
      'survivor_count': meshTable.length,
      'mesh_table': meshTable.map((s) => s.toJson()).toList(),
    };

    try {
      final response = await http
          .post(
            Uri.parse(endpoint),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200 || response.statusCode == 201) {
        return SyncResult(
          success: true,
          message: 'Synced ${meshTable.length} survivor(s) to Command Center.',
        );
      } else {
        return SyncResult(
          success: false,
          message: 'Server responded with ${response.statusCode}.',
        );
      }
    } catch (e) {
      return SyncResult(
        success: false,
        message: 'No connection to Command Center. Data saved locally.',
      );
    }
  }
}

class SyncResult {
  final bool success;
  final String message;
  const SyncResult({required this.success, required this.message});
}
