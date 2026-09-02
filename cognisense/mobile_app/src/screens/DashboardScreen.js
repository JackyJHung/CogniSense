import React, { useState, useEffect } from 'react';
import { View, Text, Button, StyleSheet, Alert } from 'react-native';
import { getCurrentUser, logout } from '../api';
import Disclaimer from '../components/Disclaimer';

export default function DashboardScreen({ navigation }) {
  const [user, setUser] = useState(null);

  useEffect(() => {
    getCurrentUser()
      .then((u) => {
        if (u) {
          setUser(u);
        } else {
          navigation.replace('Login');
        }
      })
      .catch((e) => {
        Alert.alert('Error', e.message);
        navigation.replace('Login');
      });
  }, [navigation]);

  if (!user) return <Text style={{ padding: 20 }}>Loading...</Text>;

  const h = new Date().getHours();
  const greeting = h < 11 ? 'Good morning' : h < 16 ? 'Good afternoon' : 'Good evening';

  return (
    <View style={styles.container}>
      <Text style={styles.header}>{greeting}, {user.username}</Text>

      <View style={styles.btn}><Button title="Morning check-in"  onPress={() => navigation.navigate('Morning')} /></View>
      <View style={styles.btn}><Button title="Midday check-in"   onPress={() => navigation.navigate('Midday')} /></View>
      <View style={styles.btn}><Button title="Evening check-in"  onPress={() => navigation.navigate('Evening')} /></View>
      <View style={styles.btn}><Button title="Risk & report"     onPress={() => navigation.navigate('Report')} /></View>
      <View style={styles.btn}><Button title="Daily suggestions" onPress={() => navigation.navigate('Suggestions')} /></View>
      <View style={styles.btn}><Button title="Log out" color="#a0aec0" onPress={async () => {
        await logout();
        navigation.replace('Login');
      }} /></View>
      <Disclaimer />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20, backgroundColor: '#fff' },
  header: { fontSize: 22, fontWeight: 'bold', marginBottom: 20 },
  btn: { marginBottom: 10 },
});
