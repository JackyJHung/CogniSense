import React, { useState } from 'react';
import { View, Text, TextInput, Button, StyleSheet } from 'react-native';
import { login } from '../api';
import { showApiError } from '../utils';
import Disclaimer from '../components/Disclaimer';

export default function LoginScreen({ navigation }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const handleLogin = async () => {
    try {
      await login(username, password);
      navigation.replace('Dashboard');
    } catch (e) {
      showApiError(e, 'Login failed');
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.header}>CogniSense</Text>
      <Text style={styles.sub}>Early-risk screening for memory & cognition</Text>

      <TextInput style={styles.input} placeholder="Username"
        value={username} onChangeText={setUsername} autoCapitalize="none" />
      <TextInput style={styles.input} placeholder="Password" secureTextEntry
        value={password} onChangeText={setPassword} />

      <Button title="Log in" onPress={handleLogin} />
      <View style={{ height: 10 }} />
      <Button title="Create account" onPress={() => navigation.navigate('Signup')} />
      <Disclaimer />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20, backgroundColor: '#fff' },
  header: { fontSize: 28, fontWeight: 'bold', marginTop: 20, textAlign: 'center' },
  sub: { textAlign: 'center', color: '#666', marginBottom: 30 },
  input: { borderWidth: 1, borderColor: '#ccc', borderRadius: 6, padding: 10, marginBottom: 10 },
});
