// S-track helpers. Math3D has QuatLerp (linear, enmath3d.c:397) and no slerp.
// Exp: Math has no Exp. Pow(EULER,x) (enmath.c:183, :11) misses 1e-6 at
// x=-50 (float base error x50), so Exp reduces by ln2 (Cody-Waite split,
// Math.Floor enmath.c:427), Taylor on |r|<=0.35, exact scaling by 2^n.

class STRACK_Math
{
	static float Exp(float x)
	{
		float nf;
		int n;
		float r;
		float term;
		float sum;
		int k;
		int j;
		nf = Math.Floor(x * 1.4426950408889634 + 0.5);
		n = (int)nf;
		r = x - n * 0.693145751953125;
		r = r - n * 0.000001428606765330187;
		term = 1.0;
		sum = 1.0;
		k = 1;
		while (k <= 14)
		{
			term = term * r / k;
			sum = sum + term;
			k = k + 1;
		}
		j = n;
		while (j > 0)
		{
			sum = sum * 2.0;
			j = j - 1;
		}
		while (j < 0)
		{
			sum = sum / 2.0;
			j = j + 1;
		}
		return sum;
	}

	static vector Cross(vector a, vector b)
	{
		return Vector(a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]);
	}

	static vector MulPoint(vector m[4], vector p)
	{
		return m[3] + m[0] * p[0] + m[1] * p[1] + m[2] * p[2];
	}

	static void Copy4(vector src[4], out vector dst[4])
	{
		dst[0] = src[0];
		dst[1] = src[1];
		dst[2] = src[2];
		dst[3] = src[3];
	}

	static string N(float v)
	{
		string s;
		s = v.ToString();
		s.Replace(",", ".");
		return s;
	}

	static string V(vector v)
	{
		return "[" + N(v[0]) + "," + N(v[1]) + "," + N(v[2]) + "]";
	}

	static string FrameBmp(int frame)
	{
		string n;
		n = frame.ToString();
		while (n.Length() < 6)
		{
			n = "0" + n;
		}
		return "f" + n + ".bmp";
	}

	static void Look(vector from, vector to, vector up, out vector mat[4])
	{
		vector dir;
		vector upN;
		float len;
		float dot;
		dir = to - from;
		len = dir.Length();
		if (len < 0.000001)
		{
			dir = Vector(0, 0, 1);
		}
		else
		{
			dir = dir * (1.0 / len);
		}
		upN = up;
		len = upN.Length();
		if (len < 0.000001)
		{
			upN = Vector(0, 1, 0);
		}
		else
		{
			upN = upN * (1.0 / len);
		}
		dot = vector.Dot(dir, upN);
		if (dot > 0.98 || dot < -0.98)
		{
			upN = Vector(0, 0, 1);
		}
		Math3D.DirectionAndUpMatrix(dir, upN, mat);
		mat[3] = from;
	}

	// Positive degrees: optical axis rotates toward camera +X (right).
	static void YawRight(vector mat[4], float deg, out vector o[4])
	{
		float c;
		float s;
		vector x;
		vector z;
		vector nx;
		vector nz;
		c = Math.Cos(deg * Math.DEG2RAD);
		s = Math.Sin(deg * Math.DEG2RAD);
		x = mat[0];
		z = mat[2];
		nz = z * c + x * s;
		nx = x * c - z * s;
		nz.Normalize();
		nx.Normalize();
		o[0] = nx;
		o[2] = nz;
		o[1] = Cross(nz, nx);
		o[1].Normalize();
		o[3] = mat[3];
	}

	// Positive degrees about the optical axis (+Z), x toward y.
	static void RollOptic(vector mat[4], float deg, out vector o[4])
	{
		float c;
		float s;
		vector x;
		vector y;
		c = Math.Cos(deg * Math.DEG2RAD);
		s = Math.Sin(deg * Math.DEG2RAD);
		x = mat[0];
		y = mat[1];
		o[0] = x * c + y * s;
		o[1] = y * c - x * s;
		o[0].Normalize();
		o[1].Normalize();
		o[2] = mat[2];
		o[3] = mat[3];
	}

	// Short-arc slerp. q and -q are the same rotation (flip when dot < 0).
	static void Slerp(vector a[4], vector b[4], float t, out vector o[4])
	{
		vector ra[3];
		vector rb[3];
		vector r[3];
		float qa[4];
		float qb[4];
		float q[4];
		float dot;
		float theta;
		float st;
		float w1;
		float w2;
		float len;
		ra[0] = a[0];
		ra[1] = a[1];
		ra[2] = a[2];
		rb[0] = b[0];
		rb[1] = b[1];
		rb[2] = b[2];
		Math3D.MatrixToQuat(ra, qa);
		Math3D.MatrixToQuat(rb, qb);
		dot = qa[0] * qb[0] + qa[1] * qb[1] + qa[2] * qb[2] + qa[3] * qb[3];
		if (dot < 0.0)
		{
			qb[0] = -qb[0];
			qb[1] = -qb[1];
			qb[2] = -qb[2];
			qb[3] = -qb[3];
			dot = -dot;
		}
		if (dot > 1.0)
		{
			dot = 1.0;
		}
		if (dot > 0.9995)
		{
			q[0] = qa[0] + (qb[0] - qa[0]) * t;
			q[1] = qa[1] + (qb[1] - qa[1]) * t;
			q[2] = qa[2] + (qb[2] - qa[2]) * t;
			q[3] = qa[3] + (qb[3] - qa[3]) * t;
		}
		else
		{
			theta = Math.Acos(dot);
			st = Math.Sin(theta);
			w1 = Math.Sin((1.0 - t) * theta) / st;
			w2 = Math.Sin(t * theta) / st;
			q[0] = qa[0] * w1 + qb[0] * w2;
			q[1] = qa[1] * w1 + qb[1] * w2;
			q[2] = qa[2] * w1 + qb[2] * w2;
			q[3] = qa[3] * w1 + qb[3] * w2;
		}
		len = Math.Sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
		if (len > 0.0000001)
		{
			q[0] = q[0] / len;
			q[1] = q[1] / len;
			q[2] = q[2] / len;
			q[3] = q[3] / len;
		}
		Math3D.QuatToMatrix(q, r);
		o[0] = r[0];
		o[1] = r[1];
		o[2] = r[2];
		o[3] = a[3];
	}

	static void MatQuat(vector m[4], out float q[4])
	{
		vector r[3];
		r[0] = m[0];
		r[1] = m[1];
		r[2] = m[2];
		Math3D.MatrixToQuat(r, q);
	}

	static float QuatDot(float a[4], float b[4])
	{
		return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
	}

	static string Q(float q[4])
	{
		return "[" + N(q[0]) + "," + N(q[1]) + "," + N(q[2]) + "," + N(q[3]) + "]";
	}

	// Rotation about world Y through the matrix origin.
	static void YawWorld(vector mat[4], float deg, out vector o[4])
	{
		float c;
		float s;
		int i;
		vector v;
		c = Math.Cos(deg * Math.DEG2RAD);
		s = Math.Sin(deg * Math.DEG2RAD);
		i = 0;
		while (i < 3)
		{
			v = mat[i];
			o[i] = Vector(v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c);
			o[i].Normalize();
			i = i + 1;
		}
		o[3] = mat[3];
	}

	// mode 0 = short-arc Slerp, 1 = Math3D.QuatLerp normalised, 2 = long arc.
	static void SlerpMode(vector a[4], vector b[4], float t, int mode, out vector o[4])
	{
		vector ra[3];
		vector rb[3];
		vector r[3];
		float qa[4];
		float qb[4];
		float q[4];
		float dot;
		float theta;
		float st;
		float w1;
		float w2;
		float len;
		ra[0] = a[0];
		ra[1] = a[1];
		ra[2] = a[2];
		rb[0] = b[0];
		rb[1] = b[1];
		rb[2] = b[2];
		Math3D.MatrixToQuat(ra, qa);
		Math3D.MatrixToQuat(rb, qb);
		dot = qa[0] * qb[0] + qa[1] * qb[1] + qa[2] * qb[2] + qa[3] * qb[3];
		if (mode == 1)
		{
			Math3D.QuatLerp(q, qa, qb, t);
		}
		else
		{
			if (mode == 0 && dot < 0.0)
			{
				qb[0] = -qb[0];
				qb[1] = -qb[1];
				qb[2] = -qb[2];
				qb[3] = -qb[3];
				dot = -dot;
			}
			if (dot > 1.0)
			{
				dot = 1.0;
			}
			if (dot < -1.0)
			{
				dot = -1.0;
			}
			if (mode == 0 && dot > 0.9995)
			{
				q[0] = qa[0] + (qb[0] - qa[0]) * t;
				q[1] = qa[1] + (qb[1] - qa[1]) * t;
				q[2] = qa[2] + (qb[2] - qa[2]) * t;
				q[3] = qa[3] + (qb[3] - qa[3]) * t;
			}
			else
			{
				theta = Math.Acos(dot);
				st = Math.Sin(theta);
				if (st < 0.000001 && st > -0.000001)
				{
					q[0] = qa[0];
					q[1] = qa[1];
					q[2] = qa[2];
					q[3] = qa[3];
				}
				else
				{
					w1 = Math.Sin((1.0 - t) * theta) / st;
					w2 = Math.Sin(t * theta) / st;
					q[0] = qa[0] * w1 + qb[0] * w2;
					q[1] = qa[1] * w1 + qb[1] * w2;
					q[2] = qa[2] * w1 + qb[2] * w2;
					q[3] = qa[3] * w1 + qb[3] * w2;
				}
			}
		}
		len = Math.Sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
		if (len > 0.0000001)
		{
			q[0] = q[0] / len;
			q[1] = q[1] / len;
			q[2] = q[2] / len;
			q[3] = q[3] / len;
		}
		Math3D.QuatToMatrix(q, r);
		o[0] = r[0];
		o[1] = r[1];
		o[2] = r[2];
		o[3] = a[3];
	}
};
