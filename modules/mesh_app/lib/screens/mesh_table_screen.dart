import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/mesh_service.dart';
import '../models/survivor_data.dart';

class MeshTableScreen extends StatelessWidget {
  const MeshTableScreen({super.key});

  static const _bg = Color(0xFF0D1117);
  static const _surface = Color(0xFF161B22);
  static const _card = Color(0xFF1C2128);
  static const _accent = Color(0xFF00E5FF);
  static const _green = Color(0xFF3FB950);
  static const _orange = Color(0xFFFF6A33);
  static const _red = Color(0xFFF85149);
  static const _text = Color(0xFFC9D1D9);
  static const _dim = Color(0xFF8B949E);

  @override
  Widget build(BuildContext context) {
    return Consumer<MeshService>(builder: (context, mesh, _) {
      final table = mesh.meshTable;
      return Scaffold(
        backgroundColor: _bg,
        appBar: AppBar(
          backgroundColor: _surface, elevation: 0,
          leading: IconButton(
            icon: Icon(Icons.arrow_back_ios, color: _text, size: 20),
            onPressed: () => Navigator.pop(context),
          ),
          title: Text('MESH TABLE', style: TextStyle(color: _text, fontWeight: FontWeight.w800, fontSize: 18, letterSpacing: 1.5)),
          actions: [
            if (table.isNotEmpty) IconButton(icon: Icon(Icons.delete_outline, color: _red), onPressed: () {
              showDialog(context: context, builder: (_) => AlertDialog(
                backgroundColor: _surface,
                title: Text('Clear Mesh Table?', style: TextStyle(color: _text)),
                content: Text('Remove all ${mesh.survivorCount} entries.', style: TextStyle(color: _dim)),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(context), child: Text('CANCEL', style: TextStyle(color: _dim))),
                  TextButton(onPressed: () { mesh.clearMeshTable(); Navigator.pop(context); }, child: Text('CLEAR', style: TextStyle(color: _red))),
                ],
              ));
            }),
          ],
        ),
        body: table.isEmpty
            ? Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
                Icon(Icons.wifi_tethering_off, color: _dim, size: 64),
                const SizedBox(height: 16),
                Text('No survivors detected yet.', style: TextStyle(color: _dim, fontSize: 16)),
                const SizedBox(height: 8),
                Text('Switch to Rescue Mode to start scanning.', style: TextStyle(color: _dim.withValues(alpha: 0.6), fontSize: 13)),
              ]))
            : ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: table.length,
                itemBuilder: (_, i) => _cardWidget(table[i]),
              ),
      );
    });
  }

  Widget _cardWidget(SurvivorData d) {
    final sigColor = d.rssi > -50 ? _green : (d.rssi > -70 ? _orange : _red);
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: _card, borderRadius: BorderRadius.circular(14), border: Border.all(color: sigColor.withValues(alpha: 0.3))),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.person_pin_circle, color: _accent, size: 22),
          const SizedBox(width: 8),
          Text(d.survivorId, style: TextStyle(color: _accent, fontSize: 18, fontWeight: FontWeight.w900, letterSpacing: 2, fontFamily: 'monospace')),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(color: sigColor.withValues(alpha: 0.15), borderRadius: BorderRadius.circular(6)),
            child: Text('${d.rssi} dBm  ${d.signalLabel}', style: TextStyle(color: sigColor, fontSize: 11, fontWeight: FontWeight.w700)),
          ),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 6, children: [
          _chip(Icons.swap_horiz, 'Hops: ${d.hopCount}', _accent),
          _chip(Icons.access_time, d.age, _dim),
          _chip(Icons.location_on, '${d.relayLat.toStringAsFixed(4)}, ${d.relayLng.toStringAsFixed(4)}', _orange),
          _chip(Icons.router, 'via ${d.relayNodeId}', _dim),
        ]),
      ]),
    );
  }

  Widget _chip(IconData icon, String text, Color c) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(color: c.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(6)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 13, color: c), const SizedBox(width: 4),
        Text(text, style: TextStyle(color: c, fontSize: 11, fontWeight: FontWeight.w600)),
      ]),
    );
  }
}
