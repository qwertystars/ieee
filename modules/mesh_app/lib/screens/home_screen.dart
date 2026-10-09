/// ============================================================================
/// ResQnet Mesh - Home Screen
/// ============================================================================
/// Dark-themed, high-contrast UI with mode toggle between Survivor and Rescue,
/// signal pulse animation, mesh table view, and sync-to-command functionality.
/// ============================================================================

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/mesh_service.dart';
import '../services/api_service.dart';
import '../widgets/signal_pulse.dart';
import 'mesh_table_screen.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  // ── Color Constants ─────────────────────────────────────────────────────
  static const _bg = Color(0xFF0D1117);
  static const _surface = Color(0xFF161B22);
  static const _card = Color(0xFF1C2128);
  static const _accent = Color(0xFF00E5FF);
  static const _green = Color(0xFF3FB950);
  static const _red = Color(0xFFF85149);
  static const _orange = Color(0xFFFF6A33);
  static const _textPrimary = Color(0xFFC9D1D9);
  static const _textDim = Color(0xFF8B949E);

  @override
  Widget build(BuildContext context) {
    return Consumer<MeshService>(
      builder: (context, mesh, _) {
        return Scaffold(
          backgroundColor: _bg,
          appBar: AppBar(
            backgroundColor: _surface,
            elevation: 0,
            centerTitle: true,
            title: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.cell_tower, color: _accent, size: 24),
                const SizedBox(width: 8),
                Text(
                  'ResQnet MESH',
                  style: TextStyle(
                    color: _textPrimary,
                    fontWeight: FontWeight.w800,
                    fontSize: 20,
                    letterSpacing: 1.5,
                  ),
                ),
              ],
            ),
            actions: [
              // Mesh table badge
              Stack(
                children: [
                  IconButton(
                    icon: Icon(Icons.people_alt_outlined, color: _textDim),
                    onPressed: () => Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => const MeshTableScreen(),
                      ),
                    ),
                  ),
                  if (mesh.survivorCount > 0)
                    Positioned(
                      right: 6,
                      top: 6,
                      child: Container(
                        padding: const EdgeInsets.all(4),
                        decoration: BoxDecoration(
                          color: _red,
                          shape: BoxShape.circle,
                        ),
                        child: Text(
                          '${mesh.survivorCount}',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(width: 4),
            ],
          ),
          body: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
            child: Column(
              children: [
                // ── Device ID Card ──────────────────────────────────────
                _buildDeviceCard(mesh),
                const SizedBox(height: 20),

                // ── Signal Pulse ────────────────────────────────────────
                SignalPulse(
                  isActive: mesh.isRelaying,
                  color: mesh.mode == MeshMode.survivor ? _orange : _accent,
                  size: 180,
                ),
                const SizedBox(height: 8),
                Text(
                  _statusLabel(mesh),
                  style: TextStyle(
                    color: mesh.isRelaying ? _accent : _textDim,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 1.0,
                  ),
                ),
                const SizedBox(height: 28),

                // ── Mode Toggle Buttons ─────────────────────────────────
                _buildModeButtons(context, mesh),
                const SizedBox(height: 20),

                // ── Mesh Stats Row ──────────────────────────────────────
                _buildStatsRow(mesh),
                const SizedBox(height: 20),

                // ── Sync to Command Button ──────────────────────────────
                _buildSyncButton(context, mesh),
                const SizedBox(height: 12),

                // ── Stop Button ─────────────────────────────────────────
                if (mesh.mode != MeshMode.idle)
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: OutlinedButton.icon(
                      onPressed: () => mesh.stopAll(),
                      icon: Icon(Icons.stop_circle_outlined, color: _red),
                      label: Text('STOP ALL',
                          style: TextStyle(
                              color: _red, fontWeight: FontWeight.w700)),
                      style: OutlinedButton.styleFrom(
                        side: BorderSide(color: _red.withValues(alpha: 0.5)),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Sub-widgets
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _buildDeviceCard(MeshService mesh) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: _accent.withValues(alpha: 0.15),
        ),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: _accent.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(Icons.fingerprint, color: _accent, size: 28),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('DEVICE BEACON ID',
                    style: TextStyle(
                        color: _textDim,
                        fontSize: 10,
                        letterSpacing: 1.2,
                        fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(
                  mesh.deviceId.isEmpty ? '--------' : mesh.deviceId,
                  style: TextStyle(
                    color: _accent,
                    fontSize: 24,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 4,
                    fontFamily: 'monospace',
                  ),
                ),
              ],
            ),
          ),
          // Mode indicator chip
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: _modeColor(mesh.mode).withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              _modeLabel(mesh.mode),
              style: TextStyle(
                color: _modeColor(mesh.mode),
                fontSize: 11,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildModeButtons(BuildContext context, MeshService mesh) {
    return Row(
      children: [
        // Survivor Mode
        Expanded(
          child: _ModeButton(
            label: 'SURVIVOR',
            subtitle: 'Broadcast SOS',
            icon: Icons.sos,
            color: _orange,
            isActive: mesh.mode == MeshMode.survivor,
            onTap: () => mesh.startSurvivorMode(),
          ),
        ),
        const SizedBox(width: 14),
        // Rescue Mode
        Expanded(
          child: _ModeButton(
            label: 'RESCUE',
            subtitle: 'Scan & Relay',
            icon: Icons.radar,
            color: _green,
            isActive: mesh.mode == MeshMode.rescue,
            onTap: () => mesh.startRescueMode(),
          ),
        ),
      ],
    );
  }

  Widget _buildStatsRow(MeshService mesh) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: _card,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          _StatTile(
            icon: Icons.people,
            label: 'Survivors',
            value: '${mesh.survivorCount}',
            color: _green,
          ),
          _divider(),
          _StatTile(
            icon: Icons.location_on,
            label: 'Latitude',
            value: mesh.lat.toStringAsFixed(4),
            color: _accent,
          ),
          _divider(),
          _StatTile(
            icon: Icons.location_on,
            label: 'Longitude',
            value: mesh.lng.toStringAsFixed(4),
            color: _accent,
          ),
        ],
      ),
    );
  }

  Widget _divider() => Container(
        width: 1,
        height: 36,
        margin: const EdgeInsets.symmetric(horizontal: 8),
        color: _textDim.withValues(alpha: 0.2),
      );

  Widget _buildSyncButton(BuildContext context, MeshService mesh) {
    return SizedBox(
      width: double.infinity,
      height: 54,
      child: ElevatedButton.icon(
        onPressed: mesh.survivorCount == 0
            ? null
            : () => _syncToCommand(context, mesh),
        icon: const Icon(Icons.cloud_upload_outlined, size: 22),
        label: const Text('SYNC TO COMMAND CENTER',
            style: TextStyle(fontWeight: FontWeight.w700, letterSpacing: 1)),
        style: ElevatedButton.styleFrom(
          backgroundColor: _accent,
          foregroundColor: _bg,
          disabledBackgroundColor: _surface,
          disabledForegroundColor: _textDim,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          elevation: 0,
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Helpers
  // ═══════════════════════════════════════════════════════════════════════════

  String _statusLabel(MeshService mesh) {
    switch (mesh.status) {
      case MeshStatus.scanning:
        return 'SCANNING FOR SURVIVORS...';
      case MeshStatus.advertising:
        return 'BROADCASTING SOS BEACON';
      case MeshStatus.relaying:
        return 'RELAYING MESH DATA';
      case MeshStatus.inactive:
        return 'STANDBY';
    }
  }

  String _modeLabel(MeshMode mode) {
    switch (mode) {
      case MeshMode.survivor:
        return 'SOS';
      case MeshMode.rescue:
        return 'RESCUE';
      case MeshMode.idle:
        return 'IDLE';
    }
  }

  Color _modeColor(MeshMode mode) {
    switch (mode) {
      case MeshMode.survivor:
        return _orange;
      case MeshMode.rescue:
        return _green;
      case MeshMode.idle:
        return _textDim;
    }
  }

  Future<void> _syncToCommand(BuildContext context, MeshService mesh) async {
    await mesh.refreshLocation();
    final api = ApiService();
    final result = await api.syncMeshTable(
      meshTable: mesh.meshTable,
      deviceId: mesh.deviceId,
      deviceLat: mesh.lat,
      deviceLng: mesh.lng,
    );

    if (!context.mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(result.message),
        backgroundColor: result.success ? _green : _red,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );

    // Persist locally regardless
    await mesh.persistMeshTable();
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// Private Reusable Widgets
// ═════════════════════════════════════════════════════════════════════════════

class _ModeButton extends StatelessWidget {
  final String label;
  final String subtitle;
  final IconData icon;
  final Color color;
  final bool isActive;
  final VoidCallback onTap;

  const _ModeButton({
    required this.label,
    required this.subtitle,
    required this.icon,
    required this.color,
    required this.isActive,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 14),
        decoration: BoxDecoration(
          color: isActive
              ? color.withValues(alpha: 0.15)
              : const Color(0xFF1C2128),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isActive ? color : Colors.transparent,
            width: 2,
          ),
          boxShadow: isActive
              ? [
                  BoxShadow(
                    color: color.withValues(alpha: 0.2),
                    blurRadius: 20,
                    spreadRadius: 2,
                  )
                ]
              : [],
        ),
        child: Column(
          children: [
            Icon(icon, color: color, size: 32),
            const SizedBox(height: 10),
            Text(label,
                style: TextStyle(
                    color: color,
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.5)),
            const SizedBox(height: 2),
            Text(subtitle,
                style: TextStyle(
                    color: const Color(0xFF8B949E),
                    fontSize: 11)),
          ],
        ),
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _StatTile({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          Icon(icon, color: color, size: 18),
          const SizedBox(height: 4),
          Text(value,
              style: TextStyle(
                  color: const Color(0xFFC9D1D9),
                  fontSize: 14,
                  fontWeight: FontWeight.w700)),
          Text(label,
              style: TextStyle(
                  color: const Color(0xFF8B949E), fontSize: 10)),
        ],
      ),
    );
  }
}
