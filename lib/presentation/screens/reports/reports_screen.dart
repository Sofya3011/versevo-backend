import 'package:flutter/material.dart';
import 'package:versevo_app/core/theme.dart';
import 'package:versevo_app/data/api/reports_api.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  final ReportsApi _reportsApi = ReportsApi();
  Map<String, dynamic>? _currentReport;
  bool _isLoading = false;
  String _selectedReport = 'system-health';

  final Map<String, Map<String, dynamic>> _reportConfigs = {
    'system-health': {
      'title': 'Здоровье системы',
      'icon': Icons.health_and_safety,
      'color': AppTheme.error,
      'description': 'Статистика БД, пользователи, рост'
    },
    'user-activity': {
      'title': 'Активность пользователей',
      'icon': Icons.people,
      'color': Colors.blue,
      'description': 'Регистрации, активность, документы'
    },
    'document-statistics': {
      'title': 'Статистика документов',
      'icon': Icons.insert_drive_file,
      'color': AppTheme.success,
      'description': 'Загрузки, языки, объем текста'
    },
    'translation-usage': {
      'title': 'Использование перевода',
      'icon': Icons.translate,
      'color': AppTheme.warning,
      'description': 'Переводы, языковые пары, сервисы'
    },
    'ai-analysis': {
      'title': 'AI анализ',
      'icon': Icons.psychology,
      'color': Colors.purple,
      'description': 'Анализ тональности, использование AI'
    },
  };

  Future<void> _loadReport(String reportType) async {
    setState(() {
      _isLoading = true;
      _selectedReport = reportType;
    });

    try {
      Map<String, dynamic> report;

      switch (reportType) {
        case 'system-health':
          report = await _reportsApi.getSystemHealthReport();
          break;
        case 'user-activity':
          report = await _reportsApi.getUserActivityReport();
          break;
        case 'document-statistics':
          report = await _reportsApi.getDocumentStatisticsReport();
          break;
        case 'translation-usage':
          report = await _reportsApi.getTranslationUsageReport();
          break;
        case 'ai-analysis':
          report = await _reportsApi.getAiAnalysisReport();
          break;
        default:
          report = {};
      }

      setState(() => _currentReport = report);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Ошибка загрузки отчета: $e'),
          backgroundColor: AppTheme.error,
        ),
      );
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadReport('system-health'));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Отчеты и аналитика'),
      ),
      body: Column(
        children: [
          _buildReportSelector(),
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _currentReport == null
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.bar_chart_rounded, size: 48, color: AppTheme.textTertiary),
                            const SizedBox(height: 12),
                            Text('Выберите отчет', style: Theme.of(context).textTheme.bodyMedium),
                          ],
                        ),
                      )
                    : _buildReport(_currentReport!),
          ),
        ],
      ),
    );
  }

  Widget _buildReport(Map<String, dynamic> report) {
    switch (_selectedReport) {
      case 'system-health':
        return _buildSystemHealthReport(report);
      case 'user-activity':
        return _buildUserActivityReport(report);
      case 'document-statistics':
        return _buildDocumentStatisticsReport(report);
      case 'translation-usage':
        return _buildTranslationUsageReport(report);
      case 'ai-analysis':
        return _buildAiAnalysisReport(report);
      default:
        return _buildSystemHealthReport(report);
    }
  }

  Widget _buildReportSelector() {
    return Container(
      height: 100,
      margin: const EdgeInsets.fromLTRB(16, 12, 12, 4),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: _reportConfigs.keys.length,
        separatorBuilder: (_, __) => const SizedBox(width: 10),
        itemBuilder: (context, index) {
          final key = _reportConfigs.keys.elementAt(index);
          final config = _reportConfigs[key]!;
          final isSelected = _selectedReport == key;
          return GestureDetector(
            onTap: () => _loadReport(key),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 250),
              width: 100,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: isSelected ? config['color'].withValues(alpha: 0.1) : Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: isSelected
                      ? config['color'].withValues(alpha: 0.4)
                      : AppTheme.borderLight,
                  width: isSelected ? 1.5 : 1,
                ),
                boxShadow: isSelected
                    ? [
                        BoxShadow(
                          color: config['color'].withValues(alpha: 0.15),
                          blurRadius: 10,
                          offset: const Offset(0, 2),
                        ),
                      ]
                    : [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.03),
                          blurRadius: 6,
                          offset: const Offset(0, 1),
                        ),
                      ],
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 250),
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: config['color'].withValues(alpha: isSelected ? 1.0 : 0.1),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      config['icon'],
                      color: isSelected ? Colors.white : config['color'],
                      size: 20,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    config['title'],
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                      color: isSelected ? config['color'] : AppTheme.textSecondary,
                    ),
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildMockBanner(dynamic mockWarning) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: AppTheme.warning.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.warning.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          Icon(Icons.info_outline, color: AppTheme.warning, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              mockWarning ?? 'Данные для демонстрации',
              style: TextStyle(color: AppTheme.warning, fontWeight: FontWeight.w500, fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSystemHealthReport(Map<String, dynamic> report) {
    final summary = report['summary'] ?? {};
    final tableStats = report['table_statistics'] ?? {};

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildReportHeader(
            icon: Icons.health_and_safety,
            color: AppTheme.error,
            title: 'Здоровье системы',
          ),
          if (report['is_mock'] == true)
            _buildMockBanner(report['mock_warning']),
          _buildSectionCard(
            title: 'Сводка',
            color: Colors.blue,
            child: Column(
              children: [
                _buildStatRow('Всего пользователей', '${summary['total_users']}', Icons.people, Colors.blue),
                _buildDivider(),
                _buildStatRow('Активных (7 дней)', '${summary['active_users_7d']}', Icons.trending_up, Colors.green),
                _buildDivider(),
                _buildStatRow('Активных (30 дней)', '${summary['active_users_30d']}', Icons.trending_up, AppTheme.success),
                _buildDivider(),
                _buildStatRow('Удержание', '${summary['retention_rate']}%', Icons.percent, Colors.orange),
                _buildDivider(),
                _buildStatRow('Документов', '${tableStats['documents']}', Icons.insert_drive_file, Colors.blue),
                _buildDivider(),
                _buildStatRow('Анализов', '${tableStats['document_analysis']}', Icons.analytics, Colors.purple),
                _buildDivider(),
                _buildStatRow('Цитат', '${tableStats['favorite_quotes']}', Icons.format_quote, AppTheme.secondary),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _buildSectionCard(
            title: 'Статистика таблиц БД',
            color: AppTheme.success,
            child: Wrap(
              spacing: 8,
              runSpacing: 10,
              children: tableStats.entries.map((entry) {
                return Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: AppTheme.success.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: AppTheme.success.withValues(alpha: 0.12)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        entry.key,
                        style: TextStyle(fontSize: 12, color: AppTheme.textSecondary),
                      ),
                      const SizedBox(width: 6),
                      Text(
                        '${entry.value}',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          color: AppTheme.success,
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildUserActivityReport(Map<String, dynamic> report) {
    final summary = report['summary'] ?? {};
    final data = (report['data'] as List<dynamic>?) ?? [];

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildReportHeader(
            icon: Icons.people,
            color: Colors.blue,
            title: 'Активность пользователей',
          ),
          if (report['is_mock'] == true)
            _buildMockBanner(report['mock_warning']),
          _buildSectionCard(
            title: 'Сводка',
            color: Colors.blue,
            child: Column(
              children: [
                _buildStatRow('Всего пользователей', '${summary['total_users']}', Icons.people, Colors.blue),
                _buildDivider(),
                _buildStatRow('Активных', '${summary['active_users']}', Icons.person_pin, Colors.green),
                _buildDivider(),
                _buildStatRow('Документов', '${summary['total_documents']}', Icons.insert_drive_file, Colors.blue),
                _buildDivider(),
                _buildStatRow('Прочитано слов', '${_formatNumber(summary['total_words_read'])}', Icons.chrome_reader_mode, Colors.orange),
                _buildDivider(),
                _buildStatRow('Активность', '${summary['activity_rate']}%', Icons.trending_up, AppTheme.success),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _buildSectionCard(
            title: 'Пользователи',
            color: Colors.blue,
            child: Column(
              children: data.map<Widget>((user) {
                final isActive = user['activity_status'] == 'active';
                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: (isActive ? Colors.green : Colors.grey).withValues(alpha: 0.05),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: (isActive ? Colors.green : Colors.grey).withValues(alpha: 0.15),
                    ),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: isActive ? Colors.green : Colors.grey,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(user['username'] ?? '', style: const TextStyle(fontWeight: FontWeight.w600)),
                            Text(user['email'] ?? '', style: TextStyle(fontSize: 12, color: AppTheme.textSecondary)),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          color: (isActive ? Colors.green : Colors.grey).withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          '${user['documents_count']} док.',
                          style: TextStyle(fontSize: 12, color: isActive ? Colors.green : Colors.grey),
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDocumentStatisticsReport(Map<String, dynamic> report) {
    final summary = report['summary'] ?? {};
    final data = (report['data'] as List<dynamic>?) ?? [];

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildReportHeader(
            icon: Icons.insert_drive_file,
            color: AppTheme.success,
            title: 'Статистика документов',
          ),
          if (report['is_mock'] == true)
            _buildMockBanner(report['mock_warning']),
          _buildSectionCard(
            title: 'Сводка',
            color: AppTheme.success,
            child: Column(
              children: [
                _buildStatRow('Всего документов', '${summary['total_documents']}', Icons.insert_drive_file, AppTheme.success),
                _buildDivider(),
                _buildStatRow('Всего слов', '${_formatNumber(summary['total_words'])}', Icons.text_fields, Colors.blue),
                _buildDivider(),
                _buildStatRow('Среднее слов', '${_formatNumber(summary['avg_words'])}', Icons.calculate, Colors.orange),
                _buildDivider(),
                _buildStatRow('Языков', '${summary['languages_count']}', Icons.language, Colors.purple),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _buildSectionCard(
            title: 'Документы',
            color: AppTheme.success,
            child: Column(
              children: data.map<Widget>((doc) {
                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppTheme.success.withValues(alpha: 0.04),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: AppTheme.success.withValues(alpha: 0.12)),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.description, size: 16, color: AppTheme.success),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              doc['filename'] ?? '',
                              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: Colors.blue.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              doc['language'] ?? '',
                              style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: Colors.blue),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          _buildMiniStat('Слов', '${_formatNumber(doc['word_count'])}'),
                          const SizedBox(width: 16),
                          _buildMiniStat('Чтение', '${doc['reading_time_minutes']} мин'),
                        ],
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMiniStat(String label, String value) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          '$label: ',
          style: TextStyle(fontSize: 11, color: AppTheme.textSecondary),
        ),
        Text(
          value,
          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Colors.black87),
        ),
      ],
    );
  }

  Widget _buildTranslationUsageReport(Map<String, dynamic> report) {
    final summary = report['summary'] ?? {};
    final dailyData = (report['daily_data'] as List<dynamic>?) ?? [];

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildReportHeader(
            icon: Icons.translate,
            color: AppTheme.warning,
            title: 'Использование перевода',
          ),
          if (report['is_mock'] == true)
            _buildMockBanner(report['mock_warning']),
          _buildSectionCard(
            title: 'Сводка',
            color: AppTheme.warning,
            child: Column(
              children: [
                _buildStatRow('Всего переводов', '${summary['total_translations']}', Icons.translate, AppTheme.warning),
                _buildDivider(),
                _buildStatRow('Всего символов', '${_formatNumber(summary['total_characters'])}', Icons.text_fields, Colors.blue),
                _buildDivider(),
                _buildStatRow('Уникальных', '${summary['unique_translations']}', Icons.fingerprint, Colors.purple),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _buildSectionCard(
            title: 'Ежедневная активность',
            color: AppTheme.warning,
            child: Column(
              children: dailyData.map<Widget>((day) {
                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: AppTheme.warning.withValues(alpha: 0.05),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: AppTheme.warning.withValues(alpha: 0.12)),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.calendar_today, size: 16, color: AppTheme.warning),
                      const SizedBox(width: 10),
                      Text(
                        day['date'] ?? '',
                        style: const TextStyle(fontWeight: FontWeight.w500, fontSize: 13),
                      ),
                      const Spacer(),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: AppTheme.warning.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          '${day['translation_count']}',
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            color: AppTheme.warning,
                            fontSize: 13,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        day['translation_service'] ?? '',
                        style: TextStyle(fontSize: 11, color: AppTheme.textSecondary),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAiAnalysisReport(Map<String, dynamic> report) {
    final summary = report['summary'] ?? {};
    final sentiments = (report['sentiment_distribution'] as List<dynamic>?) ?? [];

    Color _sentimentColor(String sentiment) {
      switch (sentiment) {
        case 'Положительный':
          return Colors.green;
        case 'Отрицательный':
          return AppTheme.error;
        case 'Нейтральный':
          return Colors.blueGrey;
        default:
          return Colors.grey;
      }
    }

    IconData _sentimentIcon(String sentiment) {
      switch (sentiment) {
        case 'Положительный':
          return Icons.sentiment_satisfied;
        case 'Отрицательный':
          return Icons.sentiment_dissatisfied;
        case 'Нейтральный':
          return Icons.sentiment_neutral;
        default:
          return Icons.help_outline;
      }
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildReportHeader(
            icon: Icons.psychology,
            color: Colors.purple,
            title: 'AI анализ',
          ),
          if (report['is_mock'] == true)
            _buildMockBanner(report['mock_warning']),
          _buildSectionCard(
            title: 'Сводка',
            color: Colors.purple,
            child: Column(
              children: [
                _buildStatRow('Всего анализов', '${summary['total_analysis']}', Icons.analytics, Colors.purple),
                _buildDivider(),
                _buildStatRow('Уникальных документов', '${summary['unique_documents']}', Icons.insert_drive_file, Colors.blue),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _buildSectionCard(
            title: 'Распределение тональности',
            color: Colors.purple,
            child: Column(
              children: sentiments.map<Widget>((s) {
                final sentiment = s['sentiment'] ?? '';
                final percentage = (s['percentage'] as num?)?.toDouble() ?? 0;
                final color = _sentimentColor(sentiment);
                return Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(_sentimentIcon(sentiment), size: 18, color: color),
                          const SizedBox(width: 8),
                          Text(
                            sentiment,
                            style: TextStyle(fontWeight: FontWeight.w600, color: color, fontSize: 13),
                          ),
                          const Spacer(),
                          Text(
                            '${percentage.toStringAsFixed(1)}%',
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                              color: color,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: LinearProgressIndicator(
                          value: percentage / 100,
                          backgroundColor: color.withValues(alpha: 0.1),
                          valueColor: AlwaysStoppedAnimation<Color>(color),
                          minHeight: 8,
                        ),
                      ),
                    ],
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }

  String _formatNumber(dynamic number) {
    if (number == null) return '0';
    final n = num.tryParse(number.toString()) ?? 0;
    if (n >= 1000000) return '${(n / 1000000).toStringAsFixed(1)}M';
    if (n >= 1000) return '${(n / 1000).toStringAsFixed(1)}K';
    return n.toString();
  }

  Widget _buildReportHeader({
    required IconData icon,
    required Color color,
    required String title,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: color, size: 22),
          ),
          const SizedBox(width: 12),
          Text(title, style: Theme.of(context).textTheme.headlineSmall),
        ],
      ),
    );
  }

  Widget _buildSectionCard({
    required String title,
    required Color color,
    required Widget child,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 4,
                height: 20,
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(width: 10),
              Text(title, style: Theme.of(context).textTheme.titleMedium?.copyWith(color: color)),
            ],
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }

  Widget _buildStatRow(String label, String value, IconData icon, Color color) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(icon, color: color, size: 16),
          ),
          const SizedBox(width: 12),
          Text(label, style: Theme.of(context).textTheme.bodyMedium),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              value,
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: color,
                fontSize: 14,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDivider() {
    return Divider(color: AppTheme.borderLight, height: 1, thickness: 1);
  }
}
