import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  static const Color primary = Color(0xFF6366F1);
  static const Color primaryDark = Color(0xFF4F46E5);
  static const Color primaryLight = Color(0xFFA5B4FC);
  static const Color secondary = Color(0xFFEC4899);
  static const Color accent = Color(0xFF06B6D4);
  static const Color success = Color(0xFF10B981);
  static const Color warning = Color(0xFFF59E0B);
  static const Color error = Color(0xFFEF4444);
  static const Color surfaceDark = Color(0xFF0F172A);
  static const Color surfaceLight = Color(0xFFF8FAFC);
  static const Color cardDark = Color(0xFF1E293B);
  static const Color cardLight = Color(0xFFFFFFFF);
  static const Color textPrimary = Color(0xFF1E293B);
  static const Color textSecondary = Color(0xFF64748B);
  static const Color textTertiary = Color(0xFF94A3B8);
  static const Color borderLight = Color(0xFFE2E8F0);
  static const Color borderDark = Color(0xFF334155);

  static ThemeData get lightTheme => _buildLightTheme();
  static ThemeData get darkTheme => _buildDarkTheme();

  static ThemeData _buildLightTheme() {
    final colorScheme = ColorScheme.light(
      primary: primary,
      secondary: secondary,
      tertiary: accent,
      surface: surfaceLight,
      error: error,
      onPrimary: Colors.white,
      onSecondary: Colors.white,
      onSurface: textPrimary,
      outline: borderLight,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: surfaceLight,
      textTheme: _buildTextTheme(),
      appBarTheme: _buildAppBarTheme(colorScheme),
      cardTheme: _buildCardThemeData(),
      elevatedButtonTheme: _buildElevatedButtonTheme(colorScheme),
      outlinedButtonTheme: _buildOutlinedButtonTheme(colorScheme),
      inputDecorationTheme: _buildInputDecorationTheme(colorScheme),
      bottomNavigationBarTheme: _buildBottomNavTheme(colorScheme),
      floatingActionButtonTheme: _buildFabTheme(colorScheme),
      snackBarTheme: _buildSnackBarThemeData(),
      dividerTheme: _buildDividerTheme(),
      chipTheme: _buildChipTheme(colorScheme),
      dialogTheme: _buildDialogThemeData(),
      iconTheme: IconThemeData(color: textSecondary, size: 24),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: primary,
        linearTrackColor: borderLight,
      ),
      tabBarTheme: TabBarThemeData(
        labelColor: primary,
        unselectedLabelColor: textSecondary,
        indicatorColor: primary,
      ),
      navigationBarTheme: NavigationBarThemeData(
        indicatorColor: primary.withValues(alpha: 0.12),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600, color: primary);
          }
          return GoogleFonts.inter(fontSize: 12, color: textSecondary);
        }),
      ),
    );
  }

  static ThemeData _buildDarkTheme() {
    final colorScheme = ColorScheme.dark(
      primary: primaryLight,
      secondary: secondary,
      tertiary: accent,
      surface: surfaceDark,
      error: error,
      onPrimary: Colors.white,
      onSecondary: Colors.white,
      onSurface: Colors.white,
      outline: borderDark,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: surfaceDark,
      textTheme: _buildTextTheme().apply(
        bodyColor: Colors.white,
        displayColor: Colors.white,
      ),
      appBarTheme: _buildAppBarTheme(colorScheme),
      cardTheme: _buildCardThemeData(isDark: true),
      elevatedButtonTheme: _buildElevatedButtonTheme(colorScheme),
      outlinedButtonTheme: _buildOutlinedButtonTheme(colorScheme),
      inputDecorationTheme: _buildInputDecorationTheme(colorScheme, isDark: true),
      bottomNavigationBarTheme: _buildBottomNavTheme(colorScheme, isDark: true),
      floatingActionButtonTheme: _buildFabTheme(colorScheme),
      snackBarTheme: _buildSnackBarThemeData(isDark: true),
      dividerTheme: _buildDividerTheme(isDark: true),
      chipTheme: _buildChipTheme(colorScheme, isDark: true),
      dialogTheme: _buildDialogThemeData(isDark: true),
      iconTheme: const IconThemeData(color: Colors.white70, size: 24),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: primaryLight,
        linearTrackColor: borderDark,
      ),
    );
  }

  static TextTheme _buildTextTheme() {
    return TextTheme(
      displayLarge: GoogleFonts.inter(fontSize: 34, fontWeight: FontWeight.bold, color: textPrimary, letterSpacing: -0.5),
      displayMedium: GoogleFonts.inter(fontSize: 28, fontWeight: FontWeight.bold, color: textPrimary, letterSpacing: -0.3),
      displaySmall: GoogleFonts.inter(fontSize: 24, fontWeight: FontWeight.bold, color: textPrimary),
      headlineLarge: GoogleFonts.inter(fontSize: 22, fontWeight: FontWeight.w700, color: textPrimary),
      headlineMedium: GoogleFonts.inter(fontSize: 20, fontWeight: FontWeight.w600, color: textPrimary),
      headlineSmall: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w600, color: textPrimary),
      titleLarge: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w600, color: textPrimary),
      titleMedium: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w500, color: textPrimary),
      titleSmall: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w500, color: textSecondary),
      bodyLarge: GoogleFonts.inter(fontSize: 16, color: textPrimary, height: 1.6),
      bodyMedium: GoogleFonts.inter(fontSize: 14, color: textSecondary, height: 1.5),
      bodySmall: GoogleFonts.inter(fontSize: 12, color: textTertiary, height: 1.4),
      labelLarge: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600, color: textPrimary),
      labelSmall: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w500, color: textTertiary),
    );
  }

  static AppBarTheme _buildAppBarTheme(ColorScheme colorScheme) {
    return AppBarTheme(
      backgroundColor: Colors.white,
      foregroundColor: textPrimary,
      elevation: 0,
      scrolledUnderElevation: 0.5,
      centerTitle: false,
      titleSpacing: 0,
      titleTextStyle: GoogleFonts.inter(fontSize: 18, fontWeight: FontWeight.w600, color: textPrimary),
      iconTheme: IconThemeData(color: textSecondary),
      actionsIconTheme: IconThemeData(color: textSecondary),
    );
  }

  static CardThemeData _buildCardThemeData({bool isDark = false}) {
    return CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      color: isDark ? cardDark : cardLight,
      surfaceTintColor: isDark ? cardDark : cardLight,
      shadowColor: Colors.black.withValues(alpha: isDark ? 0.3 : 0.06),
    );
  }

  static ElevatedButtonThemeData _buildElevatedButtonTheme(ColorScheme colorScheme) {
    return ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: primary,
        foregroundColor: Colors.white,
        disabledBackgroundColor: primary.withValues(alpha: 0.4),
        disabledForegroundColor: Colors.white.withValues(alpha: 0.6),
        elevation: 0,
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        textStyle: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  static OutlinedButtonThemeData _buildOutlinedButtonTheme(ColorScheme colorScheme) {
    return OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: primary,
        side: BorderSide(color: primary.withValues(alpha: 0.3)),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        textStyle: GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  static InputDecorationTheme _buildInputDecorationTheme(ColorScheme colorScheme, {bool isDark = false}) {
    final fillClr = isDark ? const Color(0xFF1E293B) : const Color(0xFFF1F5F9);
    final borderClr = isDark ? const Color(0xFF334155) : const Color(0xFFE2E8F0);
    final focusClr = primary;
    final hintClr = isDark ? const Color(0xFF64748B) : const Color(0xFF94A3B8);

    return InputDecorationTheme(
      filled: true,
      fillColor: fillClr,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: borderClr, width: 1),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: focusClr, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: error.withValues(alpha: 0.5), width: 1),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: BorderSide(color: error, width: 1.5),
      ),
      hintStyle: GoogleFonts.inter(fontSize: 14, color: hintClr),
      labelStyle: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.w500, color: textSecondary),
      prefixIconColor: textSecondary,
      suffixIconColor: textSecondary,
    );
  }

  static BottomNavigationBarThemeData _buildBottomNavTheme(ColorScheme colorScheme, {bool isDark = false}) {
    return BottomNavigationBarThemeData(
      backgroundColor: isDark ? cardDark : Colors.white,
      selectedItemColor: primary,
      unselectedItemColor: textTertiary,
      elevation: 0,
      type: BottomNavigationBarType.fixed,
      selectedLabelStyle: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w600),
      unselectedLabelStyle: GoogleFonts.inter(fontSize: 11),
    );
  }

  static FloatingActionButtonThemeData _buildFabTheme(ColorScheme colorScheme) {
    return FloatingActionButtonThemeData(
      backgroundColor: primary,
      foregroundColor: Colors.white,
      elevation: 2,
      highlightElevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    );
  }

  static SnackBarThemeData _buildSnackBarThemeData({bool isDark = false}) {
    return SnackBarThemeData(
      backgroundColor: isDark ? cardDark : const Color(0xFF1E293B),
      contentTextStyle: GoogleFonts.inter(color: Colors.white, fontSize: 14),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      behavior: SnackBarBehavior.floating,
      elevation: 2,
    );
  }

  static DividerThemeData _buildDividerTheme({bool isDark = false}) {
    return DividerThemeData(
      color: isDark ? borderDark : borderLight,
      thickness: 1,
      space: 1,
    );
  }

  static ChipThemeData _buildChipTheme(ColorScheme colorScheme, {bool isDark = false}) {
    return ChipThemeData(
      backgroundColor: isDark ? cardDark : surfaceLight,
      labelStyle: GoogleFonts.inter(fontSize: 12, color: textSecondary),
      side: BorderSide(color: isDark ? borderDark : borderLight),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    );
  }

  static DialogThemeData _buildDialogThemeData({bool isDark = false}) {
    return DialogThemeData(
      backgroundColor: isDark ? cardDark : Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    );
  }
}
