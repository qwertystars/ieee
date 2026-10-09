/// ============================================================================
/// ResQnet Mesh - Application Entry Point
/// ============================================================================
/// Initializes permissions, MeshService, and launches the dark-themed UI.
/// ============================================================================

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:permission_handler/permission_handler.dart';

import 'services/mesh_service.dart';
import 'screens/home_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Lock to portrait for field use
  await SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
  ]);

  // Dark system chrome
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
    systemNavigationBarColor: Color(0xFF0D1117),
  ));

  // Request BLE + Location permissions
  await _requestPermissions();

  // Initialize mesh service
  final meshService = MeshService();
  await meshService.initialize();
  await meshService.restoreMeshTable();

  runApp(
    ChangeNotifierProvider<MeshService>.value(
      value: meshService,
      child: const ResQnetMeshApp(),
    ),
  );
}

/// Request all permissions needed for BLE mesh networking
Future<void> _requestPermissions() async {
  await [
    Permission.bluetooth,
    Permission.bluetoothScan,
    Permission.bluetoothAdvertise,
    Permission.bluetoothConnect,
    Permission.nearbyWifiDevices,
    Permission.location,
    Permission.locationWhenInUse,
  ].request();
}

class ResQnetMeshApp extends StatelessWidget {
  const ResQnetMeshApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ResQnet Mesh',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0D1117),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF00E5FF),
          surface: Color(0xFF161B22),
        ),
        fontFamily: 'Roboto',
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}
