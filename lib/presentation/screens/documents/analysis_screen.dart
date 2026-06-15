import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:versevo_app/data/api/analysis_api.dart';
import 'package:versevo_app/data/models/document_model.dart';

class AnalysisScreen extends StatefulWidget {
  final DocumentModel document;
  const AnalysisScreen({super.key, required this.document});

  @override
  State<AnalysisScreen> createState() => _AnalysisScreenState();
}

class _AnalysisScreenState extends State<AnalysisScreen> {
  final AnalysisApi _analysisApi = AnalysisApi();
  Map<String, dynamic>? _analysisResult;
  bool _isLoading = true;
  String? _errorMessage;

  int _currentSectionIndex = 0;
  final List<String> _sectionTitles = [
    'Обзор', 'Содержание', 'Статистика'
  ];

  @override
  void initState() {
    super.initState();
    _loadAnalysis();
  }

  Future<void> _loadAnalysis() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final analysis = await _analysisApi.analyzeWithAI(
        widget.document.id,
        documentContent: widget.document.content,
      ).timeout(const Duration(seconds: 120));

      if (mounted) {
        setState(() {
          _analysisResult = analysis;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = 'Ошибка загрузки анализа. Попробуйте позже.';
          _isLoading = false;
        });
      }
    }
  }

  List<Map<String, dynamic>> _parseEntities(dynamic entities) {
    if (entities == null || entities is! List) return [];
    return entities.map((e) => e is Map ? Map<String, dynamic>.from(e) : <String, dynamic>{}).toList();
  }

  List<String> _parseKeyPoints(dynamic points) {
    if (points == null) return [];
    if (points is List) return points.map((e) => e.toString()).toList();
    return points.toString().split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
  }

  Color _getSentimentColor(String sentiment) {
    switch (sentiment.toLowerCase()) {
      case 'положительный': case 'positive': return const Color(0xFF10B981);
      case 'отрицательный': case 'negative': return const Color(0xFFEF4444);
      default: return const Color(0xFF6B7280);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.document.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w600),
            ),
            Text(
              'Анализ документа',
              style: GoogleFonts.inter(fontSize: 12, color: Colors.grey[500]),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _isLoading ? null : _loadAnalysis,
          ),
        ],
      ),
      body: _isLoading
          ? _buildLoadingView()
          : _errorMessage != null
              ? _buildErrorView()
              : Column(
                  children: [
                    _buildTabBar(),
                    Expanded(child: _buildSection(_currentSectionIndex)),
                  ],
                ),
    );
  }

  Widget _buildTabBar() {
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      height: 56,
      decoration: BoxDecoration(
        color: colorScheme.surface,
        border: Border(bottom: BorderSide(color: Colors.grey[200]!, width: 1)),
      ),
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        itemCount: _sectionTitles.length,
        itemBuilder: (context, index) {
          final isActive = _currentSectionIndex == index;
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: GestureDetector(
              onTap: () => setState(() => _currentSectionIndex = index),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                curve: Curves.easeInOut,
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                decoration: BoxDecoration(
                  gradient: isActive
                      ? LinearGradient(
                          colors: [colorScheme.primary, colorScheme.primary.withValues(alpha: 0.85)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        )
                      : null,
                  color: isActive ? null : Colors.grey[50],
                  borderRadius: BorderRadius.circular(14),
                  border: isActive ? null : Border.all(color: Colors.grey[200]!),
                  boxShadow: isActive
                      ? [
                          BoxShadow(
                            color: colorScheme.primary.withValues(alpha: 0.25),
                            blurRadius: 8,
                            offset: const Offset(0, 3),
                          ),
                        ]
                      : null,
                ),
                child: Text(
                  _sectionTitles[index],
                  style: GoogleFonts.inter(
                    fontSize: 13,
                    fontWeight: isActive ? FontWeight.w600 : FontWeight.w500,
                    color: isActive ? Colors.white : Colors.grey[600],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildLoadingView() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 64, height: 64,
            decoration: BoxDecoration(
              color: const Color(0xFF2563EB).withValues(alpha: 0.08),
              shape: BoxShape.circle,
            ),
            child: const Center(
              child: SizedBox(
                width: 28, height: 28,
                child: CircularProgressIndicator(strokeWidth: 3),
              ),
            ),
          ),
          const SizedBox(height: 20),
          Text(
            'Анализируем документ...',
            style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.w500, color: Colors.grey[600]),
          ),
          const SizedBox(height: 8),
          Text(
            widget.document.title,
            style: GoogleFonts.inter(fontSize: 13, color: Colors.grey[400]),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorView() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 80, height: 80,
              decoration: BoxDecoration(
                color: Colors.red.withValues(alpha: 0.08),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.error_outline, size: 40, color: Colors.red),
            ),
            const SizedBox(height: 20),
            Text(
              'Ошибка',
              style: GoogleFonts.inter(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            Text(
              _errorMessage ?? 'Неизвестная ошибка',
              textAlign: TextAlign.center,
              style: GoogleFonts.inter(fontSize: 14, color: Colors.grey[600], height: 1.4),
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: _loadAnalysis,
              icon: const Icon(Icons.refresh, size: 18),
              label: const Text('Повторить'),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildOverviewSection() {
    final colorScheme = Theme.of(context).colorScheme;
    final sentiment = _analysisResult?['sentiment']?.toString() ?? 'Нейтральный';
    final style = _analysisResult?['writing_style']?.toString() ?? 'Информационный';
    final keyPoints = _parseKeyPoints(_analysisResult?['key_points']);
    final overview = _analysisResult?['overview']?.toString();

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          if (overview != null && overview.isNotEmpty)
            _buildSectionCard(
              title: 'Обзор документа',
              icon: Icons.summarize,
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: colorScheme.primary.withValues(alpha: 0.04),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  overview,
                  style: GoogleFonts.inter(fontSize: 14, height: 1.6),
                  textAlign: TextAlign.justify,
                ),
              ),
            ),
          if (overview != null && overview.isNotEmpty)
            const SizedBox(height: 12),

          _buildSectionCard(
            title: 'Характеристики',
            icon: Icons.info_outline,
            child: Row(
              children: [
                _buildMiniBadge(Icons.mood, sentiment, _getSentimentColor(sentiment)),
                const SizedBox(width: 10),
                _buildMiniBadge(Icons.edit, style, Colors.purple),
                if (_analysisResult?['complexity'] != null) ...[
                  const SizedBox(width: 10),
                  _buildMiniBadge(Icons.school, _analysisResult!['complexity'].toString(), Colors.orange),
                ],
              ],
            ),
          ),
          const SizedBox(height: 12),

          if (keyPoints.isNotEmpty)
            _buildSectionCard(
              title: 'Ключевые моменты',
              icon: Icons.checklist,
              child: Column(
                children: keyPoints.take(6).map((point) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        margin: const EdgeInsets.only(top: 5),
                        width: 6, height: 6,
                        decoration: BoxDecoration(
                          color: colorScheme.primary,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          point,
                          style: GoogleFonts.inter(fontSize: 14, height: 1.4),
                        ),
                      ),
                    ],
                  ),
                )).toList(),
              ),
            ),

          const SizedBox(height: 24),
        ],
      ),
    );
  }

  Widget _buildMiniBadge(IconData icon, String label, Color color) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withValues(alpha: 0.15)),
        ),
        child: Column(
          children: [
            Icon(icon, size: 18, color: color),
            const SizedBox(height: 4),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w600, color: color),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSummarySection() {
    final summary = _analysisResult?['summary']?.toString() ?? 'Краткое содержание недоступно';
    final entities = _parseEntities(_analysisResult?['entities']);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          _buildSectionCard(
            title: 'Краткое содержание',
            icon: Icons.article,
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: Colors.grey[50],
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.grey[200]!),
              ),
              child: Text(
                summary,
                style: GoogleFonts.inter(fontSize: 14, height: 1.65),
                textAlign: TextAlign.justify,
              ),
            ),
          ),
          if (entities.isNotEmpty) ...[
            const SizedBox(height: 12),
            _buildSectionCard(
              title: 'Упоминаемые объекты',
              icon: Icons.travel_explore,
              child: Wrap(
                spacing: 8, runSpacing: 8,
                children: entities.take(12).map((entity) {
                  final word = entity['word']?.toString() ?? entity['name']?.toString() ?? '';
                  final type = entity['entity']?.toString() ?? entity['type']?.toString() ?? '';
                  late Color c;
                  if (type.contains('PER')) { c = const Color(0xFF10B981); }
                  else if (type.contains('LOC')) { c = const Color(0xFFEF4444); }
                  else if (type.contains('ORG')) { c = const Color(0xFF7C3AED); }
                  else { c = const Color(0xFF2563EB); }
                  return Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [c.withValues(alpha: 0.1), c.withValues(alpha: 0.04)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: c.withValues(alpha: 0.2)),
                    ),
                    child: Text(
                      word,
                      style: GoogleFonts.inter(fontSize: 12, color: c, fontWeight: FontWeight.w500),
                    ),
                  );
                }).toList(),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildStatsSection() {
    final stats = _analysisResult?['statistics'] is Map
        ? _analysisResult!['statistics'] as Map<String, dynamic>
        : <String, dynamic>{};

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          GridView.count(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisCount: 2,
            childAspectRatio: 1.3,
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            children: [
              _buildStatCard(Icons.description, '${widget.document.wordCount}', 'Слов', const Color(0xFF2563EB)),
              _buildStatCard(Icons.text_fields, '${widget.document.charCount}', 'Символов', const Color(0xFF7C3AED)),
              _buildStatCard(Icons.menu_book, '${widget.document.chapterCount}', 'Глав', const Color(0xFF10B981)),
              _buildStatCard(Icons.timer, '${widget.document.readingTimeMinutes}', 'Минут чтения', const Color(0xFFF59E0B)),
            ],
          ),
          const SizedBox(height: 16),

          if (stats.isNotEmpty)
            _buildSectionCard(
              title: 'Лингвистические показатели',
              icon: Icons.bar_chart,
              child: Column(
                children: [
                  if (stats['avg_sentence_length'] != null)
                    _buildStatRow('Средняя длина предложения', '${stats['avg_sentence_length']} слов'),
                  if (stats['sentence_count'] != null)
                    _buildStatRow('Количество предложений', '${stats['sentence_count']}'),
                  if (stats['paragraph_count'] != null)
                    _buildStatRow('Количество абзацев', '${stats['paragraph_count']}'),
                  if (stats['avg_word_length'] != null)
                    _buildStatRow('Средняя длина слова', '${stats['avg_word_length']} символов'),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildStatCard(IconData icon, String value, String label, Color color) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Colors.grey[200]!),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 36, height: 36,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [color.withValues(alpha: 0.12), color.withValues(alpha: 0.04)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, size: 18, color: color),
            ),
            const SizedBox(height: 8),
            Text(
              value,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: GoogleFonts.inter(fontSize: 16, fontWeight: FontWeight.bold, color: color),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: GoogleFonts.inter(fontSize: 11, color: Colors.grey[500]),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: GoogleFonts.inter(fontSize: 13, color: Colors.grey[700])),
          Text(
            value,
            style: GoogleFonts.inter(fontSize: 13, fontWeight: FontWeight.bold, color: const Color(0xFF2563EB)),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionCard({
    required String title,
    required IconData icon,
    Color? accentColor,
    required Widget child,
  }) {
    final c = accentColor ?? Theme.of(context).colorScheme.primary;
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: Colors.grey[200]!),
      ),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 32, height: 32,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [c.withValues(alpha: 0.12), c.withValues(alpha: 0.04)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(icon, size: 18, color: c),
                ),
                const SizedBox(width: 12),
                Text(
                  title,
                  style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: c),
                ),
              ],
            ),
            const SizedBox(height: 14),
            child,
          ],
        ),
      ),
    );
  }

  Widget _buildSection(int index) {
    switch (index) {
      case 0: return _buildOverviewSection();
      case 1: return _buildSummarySection();
      case 2: return _buildStatsSection();
      default: return _buildOverviewSection();
    }
  }
}
