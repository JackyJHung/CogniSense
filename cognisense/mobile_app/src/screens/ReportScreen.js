import React, { useState, useEffect } from 'react';
import { View, Text, Button, ScrollView, ActivityIndicator, StyleSheet } from 'react-native';
import { getCurrentUser, getRiskComparison } from '../api';
import { showApiError } from '../utils';
import Disclaimer from '../components/Disclaimer';

export default function ReportScreen({ navigation }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const user = await getCurrentUser();
        const rc = await getRiskComparison(user.id);
        setData(rc);
      } catch (e) {
        showApiError(e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }
  if (!data) {
    return (
      <View style={styles.container}>
        <Text>Could not load report.</Text>
        <Button title="Back" onPress={() => navigation.goBack()} />
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.header}>Risk report</Text>

      <View style={styles.summary}>
        <Text style={styles.line}>Your recent avg score:           {data.user_recent_avg_score.toFixed(2)}</Text>
        <Text style={styles.line}>Peer expected ADRD prevalence:   {data.peer_expected_prevalence_pct.toFixed(1)}%</Text>
        <Text style={styles.line}>Peer SCD rate:                   {data.scd_peer_prevalence_pct.toFixed(1)}%</Text>
      </View>

      {data.elevated_concern && (
        <View style={styles.warn}>
          <Text style={styles.warnHeader}>⚠ Attention</Text>
          <Text>{data.concern_reason}</Text>
          <Text style={styles.warnAdvice}>
            This is NOT a diagnosis. If your memory concerns are worsening, please speak with a physician.
          </Text>
        </View>
      )}

      <Text style={styles.sectionHeader}>Suggestions</Text>
      {data.suggestions.map((s, i) => (
        <Text key={i} style={styles.bullet}>• {s}</Text>
      ))}

      <Text style={styles.sectionHeader}>Sources</Text>
      {data.citations.map((c, i) => (
        <Text key={i} style={styles.citation}>– {c}</Text>
      ))}

      <View style={{ height: 16 }} />
      <Button title="Back to dashboard" onPress={() => navigation.navigate('Dashboard')} />
      <Disclaimer />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: '#fff' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { fontSize: 22, fontWeight: 'bold', marginBottom: 12 },
  summary: { padding: 12, backgroundColor: '#f7fafc', borderRadius: 6, marginBottom: 14 },
  line: { fontFamily: 'Courier', fontSize: 14, marginBottom: 4 },
  warn: { backgroundColor: '#fff3cd', borderWidth: 1, borderColor: '#facc15',
          padding: 12, borderRadius: 6, marginBottom: 14 },
  warnHeader: { fontSize: 16, fontWeight: 'bold', marginBottom: 6 },
  warnAdvice: { marginTop: 8, fontStyle: 'italic' },
  sectionHeader: { fontSize: 16, fontWeight: 'bold', marginTop: 10, marginBottom: 6 },
  bullet: { marginBottom: 6, lineHeight: 20 },
  citation: { fontSize: 11, color: '#555', marginBottom: 4 },
});
