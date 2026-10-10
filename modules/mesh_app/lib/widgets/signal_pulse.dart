/// ============================================================================
/// ResQnet Mesh - Signal Pulse Animation Widget
/// ============================================================================
/// A radiating concentric circle animation that indicates the device is
/// actively scanning or advertising via BLE.
/// ============================================================================

import 'dart:math';
import 'package:flutter/material.dart';

class SignalPulse extends StatefulWidget {
  /// Whether the pulse is actively animating
  final bool isActive;

  /// Color of the pulse rings
  final Color color;

  /// Size of the widget
  final double size;

  const SignalPulse({
    super.key,
    required this.isActive,
    this.color = const Color(0xFF00E5FF),
    this.size = 160,
  });

  @override
  State<SignalPulse> createState() => _SignalPulseState();
}

class _SignalPulseState extends State<SignalPulse>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    );
    if (widget.isActive) _controller.repeat();
  }

  @override
  void didUpdateWidget(SignalPulse oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_controller.isAnimating) {
      _controller.repeat();
    } else if (!widget.isActive && _controller.isAnimating) {
      _controller.stop();
      _controller.reset();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          return CustomPaint(
            painter: _PulsePainter(
              progress: _controller.value,
              color: widget.color,
              isActive: widget.isActive,
            ),
            child: child,
          );
        },
        // Center dot
        child: Center(
          child: Container(
            width: 20,
            height: 20,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: widget.isActive
                  ? widget.color
                  : widget.color.withValues(alpha: 0.3),
              boxShadow: widget.isActive
                  ? [
                      BoxShadow(
                        color: widget.color.withValues(alpha: 0.6),
                        blurRadius: 16,
                        spreadRadius: 4,
                      ),
                    ]
                  : [],
            ),
          ),
        ),
      ),
    );
  }
}

class _PulsePainter extends CustomPainter {
  final double progress;
  final Color color;
  final bool isActive;

  _PulsePainter({
    required this.progress,
    required this.color,
    required this.isActive,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (!isActive) return;

    final center = Offset(size.width / 2, size.height / 2);
    final maxRadius = size.width / 2;

    // Draw 3 concentric expanding rings at staggered phases
    for (int i = 0; i < 3; i++) {
      final phase = (progress + i * 0.33) % 1.0;
      final radius = maxRadius * phase;
      final opacity = (1.0 - phase).clamp(0.0, 0.6);

      final paint = Paint()
        ..color = color.withValues(alpha: opacity)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5;

      canvas.drawCircle(center, radius, paint);
    }
  }

  @override
  bool shouldRepaint(_PulsePainter old) =>
      old.progress != progress || old.isActive != isActive;
}
